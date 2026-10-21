from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

import requests
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ..models import Payment
from ..services.gateways import GatewayTransaction, get_gateway
from ..services.gateways.wompi import WompiGateway
from ..services.signature import event_checksum, integrity_signature
from .test_api import CLIENT, REQ, TEST_PAYMENTS_SETTINGS, AppApiTestCase

WOMPI = {
    'PUBLIC_KEY': 'pub_test_abc',
    'PRIVATE_KEY': 'prv_test_abc',
    'EVENTS_SECRET': 'test_events_abc',
    'INTEGRITY_SECRET': 'test_integrity_abc',
    'BASE_URL': 'https://sandbox.wompi.co/v1',
}
WOMPI_SETTINGS = dict(TEST_PAYMENTS_SETTINGS, MODE='wompi', WOMPI=WOMPI)


def wompi_gateway():
    return WompiGateway(WOMPI['PUBLIC_KEY'], WOMPI['PRIVATE_KEY'], WOMPI['INTEGRITY_SECRET'],
                        WOMPI['EVENTS_SECRET'], WOMPI['BASE_URL'])


def http_response(payload, status=200):
    response = mock.Mock(status_code=status)
    response.json.return_value = payload
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(str(status))
    return response


class WompiGatewayTests(SimpleTestCase):

    def test_checkout_url_has_web_checkout_params_and_integrity_signature(self):
        session = wompi_gateway().create_transaction('ADS-REF-1', 8500000, 'COP', 'adsapp://payment-result')

        url = urlparse(session.checkout_url)
        self.assertEqual(f"{url.scheme}://{url.netloc}{url.path}", 'https://checkout.wompi.co/p/')
        params = {key: values[0] for key, values in parse_qs(url.query).items()}
        self.assertEqual(params, {
            'public-key': 'pub_test_abc',
            'currency': 'COP',
            'amount-in-cents': '8500000',
            'reference': 'ADS-REF-1',
            'signature:integrity': integrity_signature('ADS-REF-1', 8500000, 'COP', 'test_integrity_abc'),
        })

    def test_requires_keys(self):
        with self.assertRaises(ValueError):
            WompiGateway('', 'prv', 'i', 'e', WOMPI['BASE_URL'])

    @override_settings(PAYMENTS=WOMPI_SETTINGS, DJANGO_ENV='production')
    def test_get_gateway_returns_wompi_in_production(self):
        self.assertIsInstance(get_gateway(), WompiGateway)

    @override_settings(PAYMENTS=dict(WOMPI_SETTINGS, WOMPI=dict(WOMPI, PRIVATE_KEY='')))
    def test_get_gateway_without_keys_is_misconfigured(self):
        with self.assertRaises(ImproperlyConfigured):
            get_gateway()

    @mock.patch('payments.services.gateways.wompi.requests.get')
    def test_find_transaction_uses_private_key_and_prefers_approved(self, get):
        get.return_value = http_response({'data': [
            {'id': 't-1', 'reference': 'ADS-REF-1', 'status': 'DECLINED', 'amount_in_cents': 8500000},
            {'id': 't-2', 'reference': 'ADS-REF-1', 'status': 'APPROVED', 'amount_in_cents': 8500000},
        ]})

        found = wompi_gateway().find_transaction('ADS-REF-1')

        self.assertEqual(found, GatewayTransaction('t-2', 'APPROVED', 8500000))
        args, kwargs = get.call_args
        self.assertEqual(args[0], 'https://sandbox.wompi.co/v1/transactions')
        self.assertEqual(kwargs['params'], {'reference': 'ADS-REF-1'})
        self.assertEqual(kwargs['headers'], {'Authorization': 'Bearer prv_test_abc'})
        self.assertIn('timeout', kwargs)

    @mock.patch('payments.services.gateways.wompi.requests.get')
    def test_find_transaction_failures_return_none(self, get):
        cases = [
            http_response({'data': []}),
            http_response({}, status=500),
            requests.ConnectionError('sin red'),
            http_response({'data': [{'reference': 'OTRA', 'status': 'APPROVED', 'amount_in_cents': 1}]}),
        ]
        for case in cases:
            with self.subTest(case=case):
                if isinstance(case, Exception):
                    get.side_effect, get.return_value = case, None
                else:
                    get.side_effect, get.return_value = None, case
                self.assertIsNone(wompi_gateway().find_transaction('ADS-REF-1'))


@override_settings(PAYMENTS=WOMPI_SETTINGS)
class WompiPaymentFlowTests(AppApiTestCase):

    def setUp(self):
        super().setUp()
        self.set_request(status='completed', quoted_price=85000, quote_status='accepted')
        find = mock.patch.object(WompiGateway, 'find_transaction', return_value=None)
        self.find = find.start()
        self.addCleanup(find.stop)

    def start(self):
        return self.api(CLIENT).post(reverse('payments:payment-list'), {'service_request_id': REQ}, format='json')

    def signed_event(self, reference, status, amount=8500000):
        event = {
            'event': 'transaction.updated',
            'data': {'transaction': {'id': 'wompi-1', 'amount_in_cents': amount, 'reference': reference,
                                     'status': status}},
            'environment': 'test',
            'signature': {'properties': ['transaction.id', 'transaction.status', 'transaction.amount_in_cents'],
                          'checksum': ''},
            'timestamp': 1792169400,
        }
        event['signature']['checksum'] = event_checksum(event, WOMPI['EVENTS_SECRET'])
        return event

    def test_start_payment_returns_wompi_checkout(self):
        response = self.start()
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['data']['checkout_url'].startswith('https://checkout.wompi.co/p/?'))
        self.assertEqual(Payment.objects.get().gateway, 'wompi')

    def test_webhook_with_wompi_signature_approves(self):
        reference = self.start().json()['data']['reference']
        event = self.signed_event(reference, 'APPROVED')
        response = self.client.post(reverse('payments:webhook'), event, content_type='application/json',
                                    HTTP_X_EVENT_CHECKSUM=event['signature']['checksum'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.get().status, 'APPROVED')
        self.assertEqual(self.request_data()['payment_status'], 'approved')

    def test_expired_pending_approved_in_wompi_is_reconciled(self):
        reference = self.start().json()['data']['reference']
        Payment.objects.update(created_at=timezone.now() - timedelta(minutes=31))
        self.find.return_value = GatewayTransaction('wompi-1', 'APPROVED', 8500000)

        response = self.start()

        self.assertEqual(response.status_code, 409)
        payment = Payment.objects.get(reference=reference)
        self.assertEqual(payment.status, 'APPROVED')
        self.assertTrue(payment.events.filter(event_type='local.reconciled').exists())
        self.assertEqual(self.request_data()['payment_status'], 'approved')
        self.assertIn(('fcm-worker', 'payment_approved'), self.sent_notifications())
        self.assertEqual(Payment.objects.count(), 1)

    def test_expired_pending_still_processing_in_wompi_is_reused(self):
        reference = self.start().json()['data']['reference']
        Payment.objects.update(created_at=timezone.now() - timedelta(minutes=31))
        self.find.return_value = GatewayTransaction('wompi-1', 'PENDING', 8500000)

        response = self.start()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['reference'], reference)

    def test_expired_pending_declined_in_wompi_allows_new_attempt(self):
        reference = self.start().json()['data']['reference']
        Payment.objects.update(created_at=timezone.now() - timedelta(minutes=31))
        self.find.return_value = GatewayTransaction('wompi-1', 'DECLINED', 8500000)

        response = self.start()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Payment.objects.get(reference=reference).status, 'DECLINED')
        self.assertEqual(Payment.objects.count(), 2)


class WompiRedirectTests(SimpleTestCase):
    """Wompi solo acepta redirect-url https: el deep link pasa por /api/payments/return/."""

    def gateway(self, public_base_url='https://ads-api.onrender.com'):
        return WompiGateway(WOMPI['PUBLIC_KEY'], WOMPI['PRIVATE_KEY'], WOMPI['INTEGRITY_SECRET'],
                            WOMPI['EVENTS_SECRET'], WOMPI['BASE_URL'], public_base_url)

    def redirect_param(self, gateway, redirect_url):
        url = gateway.create_transaction('ADS-REF-1', 8500000, 'COP', redirect_url).checkout_url
        return parse_qs(urlparse(url).query).get('redirect-url', [None])[0]

    def test_deep_link_becomes_https_return_page(self):
        self.assertEqual(self.redirect_param(self.gateway(), 'adsapp://payment-result?request_id=-Abc123'),
                         'https://ads-api.onrender.com/api/payments/return/?request_id=-Abc123')
        self.assertEqual(self.redirect_param(self.gateway(), 'adsapp://payment-result'),
                         'https://ads-api.onrender.com/api/payments/return/')

    def test_without_public_url_redirect_is_omitted(self):
        self.assertIsNone(self.redirect_param(self.gateway(''), 'adsapp://payment-result?request_id=x'))

    def test_return_page_opens_only_the_app(self):
        response = self.client.get(reverse('payments:return'), {'request_id': '-Abc123', 'id': 'wompi-1'})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('intent://payment-result?request_id=-Abc123#Intent;scheme=adsapp;package=com.project.ads;end',
                      html)
        self.assertIn('window.location.replace("adsapp://payment', html)

        html = self.client.get(reverse('payments:return'), {'request_id': 'https://evil.example/x'}).content.decode()
        self.assertNotIn('evil.example', html)
        self.assertIn('href="intent://payment-result#Intent;scheme=adsapp;package=com.project.ads;end"', html)
