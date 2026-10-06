import copy
import hashlib
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .guards import check_payment_mode
from .models import Payment, PaymentEvent
from .services.gateways import get_gateway
from .services.payment_service import EventResult, FirebaseSyncError, payment_service
from .services.gateways.base import BaseGateway
from .services.signature import (
    event_checksum,
    integrity_signature,
    verify_event_checksum,
)

EVENTS_SECRET = 'test_events_secret'


def _sha256(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _build_event(status='APPROVED'):
    """Evento con la estructura documentada por Wompi, firmado con EVENTS_SECRET."""
    event = {
        'event': 'transaction.updated',
        'data': {
            'transaction': {
                'id': '1234-1610641025-49201',
                'amount_in_cents': 4490000,
                'reference': 'ADS-REF-001',
                'status': status,
            }
        },
        'environment': 'test',
        'signature': {
            'properties': ['transaction.id', 'transaction.status', 'transaction.amount_in_cents'],
            'checksum': '',
        },
        'timestamp': 1530291411,
        'sent_at': '2018-07-20T16:45:05.000Z',
    }
    event['signature']['checksum'] = event_checksum(event, EVENTS_SECRET)
    return event


class IntegritySignatureTests(SimpleTestCase):

    def test_concatenation_without_expiration(self):
        expected = _sha256('ADS-REF-0012990000COPsecret')
        self.assertEqual(integrity_signature('ADS-REF-001', 2990000, 'COP', 'secret'), expected)

    def test_expiration_goes_before_secret(self):
        expected = _sha256('ADS-REF-0012990000COP2026-10-06T15:00:00.000Zsecret')
        signature = integrity_signature(
            'ADS-REF-001', 2990000, 'COP', 'secret', expiration_time='2026-10-06T15:00:00.000Z'
        )
        self.assertEqual(signature, expected)

    def test_rejects_non_integer_amounts(self):
        for amount in (29900.5, '2990000', True, None):
            with self.assertRaises(ValueError):
                integrity_signature('ADS-REF-001', amount, 'COP', 'secret')

    def test_rejects_non_positive_amounts(self):
        for amount in (0, -100):
            with self.assertRaises(ValueError):
                integrity_signature('ADS-REF-001', amount, 'COP', 'secret')

    def test_rejects_missing_secret(self):
        with self.assertRaises(ValueError):
            integrity_signature('ADS-REF-001', 2990000, 'COP', '')


class EventChecksumTests(SimpleTestCase):

    def test_concatenation_matches_wompi_docs(self):
        # Regla documentada: valores de properties + timestamp + secreto
        event = _build_event()
        expected = _sha256('1234-1610641025-49201APPROVED44900001530291411' + EVENTS_SECRET).upper()
        self.assertEqual(event_checksum(event, EVENTS_SECRET), expected)

    def test_valid_event(self):
        self.assertTrue(verify_event_checksum(_build_event(), EVENTS_SECRET))

    def test_checksum_comparison_is_case_insensitive(self):
        event = _build_event()
        event['signature']['checksum'] = event['signature']['checksum'].lower()
        self.assertTrue(verify_event_checksum(event, EVENTS_SECRET))

    def test_wrong_secret(self):
        self.assertFalse(verify_event_checksum(_build_event(), 'otro_secreto'))

    def test_tampered_status(self):
        event = _build_event('DECLINED')
        event['data']['transaction']['status'] = 'APPROVED'
        self.assertFalse(verify_event_checksum(event, EVENTS_SECRET))

    def test_tampered_amount(self):
        event = _build_event()
        event['data']['transaction']['amount_in_cents'] = 100
        self.assertFalse(verify_event_checksum(event, EVENTS_SECRET))

    def test_header_must_match_when_present(self):
        event = _build_event()
        checksum = event['signature']['checksum']
        self.assertTrue(verify_event_checksum(event, EVENTS_SECRET, header_checksum=checksum))
        self.assertFalse(verify_event_checksum(event, EVENTS_SECRET, header_checksum='ABC'))

    def test_malformed_events_are_invalid(self):
        event = _build_event()
        missing_property = copy.deepcopy(event)
        missing_property['signature']['properties'].append('transaction.no_existe')
        no_timestamp = copy.deepcopy(event)
        del no_timestamp['timestamp']

        for malformed in ({}, None, missing_property, no_timestamp):
            self.assertFalse(verify_event_checksum(malformed, EVENTS_SECRET))


class _DummyGateway(BaseGateway):
    name = 'dummy'

    def create_transaction(self, reference, amount_in_cents, currency, redirect_url=None):
        raise NotImplementedError


class BaseGatewayTests(SimpleTestCase):

    def setUp(self):
        self.gateway = _DummyGateway('integrity', EVENTS_SECRET)

    def test_requires_secrets(self):
        with self.assertRaises(ValueError):
            _DummyGateway('', EVENTS_SECRET)

    def test_parse_event(self):
        event = self.gateway.parse_event(_build_event())
        self.assertEqual(event.reference, 'ADS-REF-001')
        self.assertEqual(event.status, 'APPROVED')
        self.assertEqual(event.amount_in_cents, 4490000)
        self.assertEqual(event.transaction_id, '1234-1610641025-49201')

    def test_parse_event_rejects_invalid_structure(self):
        with self.assertRaises(ValueError):
            self.gateway.parse_event({'event': 'transaction.updated', 'data': {}})

    def test_parse_event_rejects_float_amount(self):
        event = _build_event()
        event['data']['transaction']['amount_in_cents'] = 4490000.0
        with self.assertRaises(ValueError):
            self.gateway.parse_event(event)


class PaymentModeGuardTests(SimpleTestCase):

    def test_mock_forbidden_in_production(self):
        with self.assertRaises(ImproperlyConfigured):
            check_payment_mode('production', 'mock')

    def test_allowed_combinations(self):
        check_payment_mode('development', 'mock')
        check_payment_mode('development', 'wompi')
        check_payment_mode('production', 'wompi')

    def test_invalid_mode(self):
        with self.assertRaises(ImproperlyConfigured):
            check_payment_mode('development', 'paypal')


class PaymentTransitionTests(SimpleTestCase):

    def _payment(self, status):
        return Payment(status=status)

    def test_pending_can_be_resolved(self):
        payment = self._payment(Payment.STATUS_PENDING)
        for new_status in (Payment.STATUS_APPROVED, Payment.STATUS_DECLINED, Payment.STATUS_ERROR):
            self.assertTrue(payment.can_transition_to(new_status))

    def test_approved_only_can_be_voided(self):
        payment = self._payment(Payment.STATUS_APPROVED)
        self.assertTrue(payment.can_transition_to(Payment.STATUS_VOIDED))
        self.assertFalse(payment.can_transition_to(Payment.STATUS_PENDING))
        self.assertFalse(payment.can_transition_to(Payment.STATUS_DECLINED))

    def test_final_states_do_not_change(self):
        for status in (Payment.STATUS_DECLINED, Payment.STATUS_ERROR, Payment.STATUS_VOIDED):
            payment = self._payment(status)
            for new_status, _ in Payment.STATUSES:
                self.assertFalse(payment.can_transition_to(new_status))


TEST_PAYMENTS_SETTINGS = {
    'MODE': 'mock',
    'CURRENCY': 'COP',
    'WOMPI': {},
    'MOCK': {
        'EVENTS_SECRET': 'mock_events_test',
        'INTEGRITY_SECRET': 'mock_integrity_test',
        'CHECKOUT_BASE_URL': 'http://testserver',
    },
}


@override_settings(PAYMENTS=TEST_PAYMENTS_SETTINGS, DJANGO_ENV='development')
class PaymentFlowTestCase(TestCase):
    """Base: Firebase simulado y un pago PENDING de 50.000 COP."""

    def setUp(self):
        self.firebase = mock.MagicMock()
        self.firebase.get_data.return_value = None
        patcher = mock.patch.object(payment_service, 'firebase', self.firebase)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.gateway = get_gateway()
        self.payment, self.session = payment_service.create_payment(
            service_request_id='req-1',
            client_uid='client-1',
            worker_uid='worker-1',
            amount_in_cents=5000000,
            redirect_url='adsapp://payment-result',
        )
        self.firebase.reset_mock()

    def event(self, status, amount_in_cents=None, reference=None, transaction_id='mock-1-11111'):
        return self.gateway.build_event(
            reference=reference or self.payment.reference,
            transaction_id=transaction_id,
            status=status,
            amount_in_cents=amount_in_cents if amount_in_cents is not None else self.payment.amount_in_cents,
            currency='COP',
        )

    def post_webhook(self, payload, header=None):
        headers = {'HTTP_X_EVENT_CHECKSUM': header} if header else {}
        return self.client.post(reverse('payments:webhook'), payload, content_type='application/json', **headers)


class CreatePaymentTests(PaymentFlowTestCase):

    def test_payment_starts_pending_with_signed_checkout(self):
        self.assertEqual(self.payment.status, Payment.STATUS_PENDING)
        self.assertEqual(self.payment.gateway, 'mock')
        self.assertTrue(self.payment.reference.startswith('ADS-'))

        query = parse_qs(urlparse(self.session.checkout_url).query)
        self.assertEqual(query['reference'], [self.payment.reference])
        self.assertEqual(query['amount-in-cents'], ['5000000'])
        self.assertEqual(query['signature:integrity'], [integrity_signature(
            self.payment.reference, 5000000, 'COP', 'mock_integrity_test')])

    def test_references_are_unique(self):
        _, other = payment_service.create_payment('req-2', 'c', 'w', 100000)
        self.assertNotEqual(other.reference, self.payment.reference)


class WebhookTests(PaymentFlowTestCase):

    def test_approved_event_updates_payment_and_firebase(self):
        response = self.post_webhook(self.event('APPROVED'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['outcome'], EventResult.APPLIED)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_APPROVED)
        self.assertEqual(self.payment.gateway_transaction_id, 'mock-1-11111')
        self.assertEqual(self.payment.events.count(), 1)

        path, data = self.firebase.update_data.call_args.args
        self.assertEqual(path, 'requests/req-1')
        self.assertEqual(data['payment_status'], 'approved')
        self.assertEqual(data['payment_reference'], self.payment.reference)

    def test_duplicate_event_is_idempotent(self):
        payload = self.event('APPROVED')
        self.post_webhook(payload)
        response = self.post_webhook(payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['outcome'], EventResult.DUPLICATE)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_APPROVED)
        self.assertEqual(self.payment.events.count(), 2)

    def test_invalid_checksum_is_rejected_and_logged(self):
        payload = self.event('DECLINED')
        payload['data']['transaction']['status'] = 'APPROVED'
        response = self.post_webhook(payload)

        self.assertEqual(response.status_code, 401)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_PENDING)
        logged = PaymentEvent.objects.get()
        self.assertFalse(logged.checksum_valid)
        self.assertIsNone(logged.payment)
        self.firebase.update_data.assert_not_called()

    def test_header_checksum_must_match(self):
        response = self.post_webhook(self.event('APPROVED'), header='ABC123')
        self.assertEqual(response.status_code, 401)

    def test_event_signed_with_other_secret_is_rejected(self):
        payload = self.event('APPROVED')
        payload['signature']['checksum'] = event_checksum(payload, 'otro_secreto')
        self.assertEqual(self.post_webhook(payload).status_code, 401)

    def test_amount_mismatch_is_ignored(self):
        response = self.post_webhook(self.event('APPROVED', amount_in_cents=100))

        self.assertEqual(response.json()['data']['outcome'], EventResult.IGNORED)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_PENDING)

    def test_final_state_does_not_change(self):
        self.post_webhook(self.event('DECLINED'))
        response = self.post_webhook(self.event('APPROVED', transaction_id='mock-2-22222'))

        self.assertEqual(response.json()['data']['outcome'], EventResult.IGNORED)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_DECLINED)

    def test_unknown_reference_is_acknowledged_and_logged(self):
        response = self.post_webhook(self.event('APPROVED', reference='ADS-NO-EXISTE'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['outcome'], EventResult.UNKNOWN_REFERENCE)
        self.assertTrue(PaymentEvent.objects.filter(payment=None, checksum_valid=True).exists())

    def test_malformed_signed_event(self):
        payload = self.event('APPROVED')
        del payload['data']['transaction']['reference']
        payload['signature']['checksum'] = self.gateway.compute_event_checksum(payload)
        self.assertEqual(self.post_webhook(payload).status_code, 400)

    def test_firebase_failure_returns_500_and_retry_resyncs(self):
        payload = self.event('APPROVED')
        self.firebase.update_data.side_effect = Exception('Firebase caído')
        response = self.post_webhook(payload)

        self.assertEqual(response.status_code, 500)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_APPROVED)

        self.firebase.update_data.side_effect = None
        response = self.post_webhook(payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.firebase.update_data.call_args.args[1]['payment_status'], 'approved')

    def test_webhook_does_not_require_jwt(self):
        # Sin credenciales: la autenticidad la da el checksum, no el JWT
        self.assertEqual(self.post_webhook(self.event('APPROVED')).status_code, 200)


class FirebaseSyncTests(PaymentFlowTestCase):

    def test_stale_payment_does_not_overwrite_newer_attempt(self):
        self.firebase.get_data.return_value = 'ADS-REINTENTO-NUEVO'
        payment_service.process_event(self.event('DECLINED'))
        self.firebase.update_data.assert_not_called()

    def test_late_approval_always_syncs(self):
        self.firebase.get_data.return_value = 'ADS-REINTENTO-NUEVO'
        payment_service.process_event(self.event('APPROVED'))
        self.assertEqual(self.firebase.update_data.call_args.args[1]['payment_reference'], self.payment.reference)

    def test_sync_error_is_raised(self):
        self.firebase.update_data.side_effect = Exception('timeout')
        with self.assertRaises(FirebaseSyncError):
            payment_service.sync_to_firebase(self.payment)


class MockCheckoutTests(PaymentFlowTestCase):

    def checkout_path(self):
        parsed = urlparse(self.session.checkout_url)
        return f"{parsed.path}?{parsed.query}"

    def post_outcome(self, outcome, **overrides):
        query = {k: v[0] for k, v in parse_qs(urlparse(self.session.checkout_url).query).items()}
        query.update(overrides)
        query['outcome'] = outcome
        return self.client.post(urlparse(self.session.checkout_url).path, query)

    def test_get_shows_checkout(self):
        response = self.client.get(self.checkout_path())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.payment.reference)
        self.assertContains(response, '$50.000')
        self.assertContains(response, 'Simular aprobado')

    def test_tampered_amount_is_rejected(self):
        path = self.checkout_path().replace('amount-in-cents=5000000', 'amount-in-cents=100')
        response = self.client.get(path)
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, 'Simular aprobado', status_code=400)

    def test_approve_redirects_to_app_and_updates_payment(self):
        response = self.post_outcome('approved')

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('adsapp://payment-result?id=mock-'))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_APPROVED)
        self.assertTrue(self.payment.events.get().checksum_valid)

    def test_decline_and_error(self):
        self.post_outcome('declined')
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_DECLINED)

        _, session = payment_service.create_payment('req-1', 'client-1', 'worker-1', 5000000)
        self.session = session
        self.post_outcome('error')
        self.assertEqual(Payment.objects.get(reference=session.reference).status, Payment.STATUS_ERROR)

    def test_tampered_post_is_rejected(self):
        response = self.post_outcome('approved', **{'amount-in-cents': '100'})
        self.assertEqual(response.status_code, 400)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_PENDING)

    def test_already_processed_payment(self):
        self.post_outcome('approved')
        response = self.post_outcome('declined')
        self.assertEqual(response.status_code, 409)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_APPROVED)

    def test_unsafe_redirect_scheme_is_rejected_before_processing(self):
        response = self.post_outcome('approved', **{'redirect-url': 'javascript:alert(1)'})
        self.assertEqual(response.status_code, 400)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_PENDING)
        self.assertFalse(PaymentEvent.objects.exists())

    def test_not_available_outside_mock_mode(self):
        wompi_settings = dict(TEST_PAYMENTS_SETTINGS, MODE='wompi')
        with override_settings(PAYMENTS=wompi_settings):
            self.assertEqual(self.client.get(self.checkout_path()).status_code, 404)


class GetGatewayTests(SimpleTestCase):

    @override_settings(PAYMENTS=TEST_PAYMENTS_SETTINGS, DJANGO_ENV='production')
    def test_mock_refused_at_runtime_in_production(self):
        with self.assertRaises(ImproperlyConfigured):
            get_gateway()

    @override_settings(PAYMENTS=dict(
        TEST_PAYMENTS_SETTINGS,
        MOCK={'EVENTS_SECRET': '', 'INTEGRITY_SECRET': '', 'CHECKOUT_BASE_URL': 'http://x'},
    ))
    def test_mock_requires_secrets(self):
        with self.assertRaises(ValueError):
            get_gateway()
