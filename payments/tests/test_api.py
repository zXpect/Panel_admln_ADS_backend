import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from worker_verification.models import SystemConfig

from ..models import Payment, PaymentEvent
from ..services.gateways import get_gateway
from ..services.notification_service import notification_service
from ..services.payment_service import payment_service
from ..services.service_request_service import service_request_service
from .fakes import FakeFirebase, app_token, patch_verify_id_token

CLIENT, WORKER, OTHER = 'client-1', 'worker-1', 'intruso'
REQ = 'req-1'

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


def initial_data(**request_overrides):
    request = {
        'client_id': CLIENT, 'worker_id': WORKER, 'worker_name': 'Ana',
        'service_type': 'Plomería', 'address': 'Calle 1', 'status': 'pending',
        'is_rated': False,
    }
    request.update(request_overrides)
    return {
        'requests': {REQ: request},
        'User': {'Trabajadores': {WORKER: {'name': 'Ana', 'rating': 4.0, 'totalRatings': 2}}},
        'Tokens': {CLIENT: {'token': 'fcm-client'}, WORKER: {'token': 'fcm-worker'}},
    }


@override_settings(PAYMENTS=TEST_PAYMENTS_SETTINGS, DJANGO_ENV='development')
class AppApiTestCase(TestCase):
    """Firebase en memoria, FCM simulado y tokens de la app con la forma real (RS256)."""

    def setUp(self):
        cache.clear()  # contadores de throttling
        self.fb = FakeFirebase(initial_data())
        for service in (payment_service, service_request_service, notification_service):
            patcher = mock.patch.object(service, 'firebase', self.fb)
            patcher.start()
            self.addCleanup(patcher.stop)

        verify = patch_verify_id_token()
        verify.start()
        self.addCleanup(verify.stop)

        send = mock.patch('payments.services.notification_service.messaging.send')
        self.fcm_send = send.start()
        self.addCleanup(send.stop)

    def api(self, uid=None):
        client = APIClient()
        if uid:
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {app_token(uid)}")
        return client

    def request_data(self):
        return self.fb.get_data(f"requests/{REQ}")

    def set_request(self, **values):
        self.fb.update_data(f"requests/{REQ}", values)

    def sent_notifications(self):
        """[(token, type)] de los mensajes FCM enviados."""
        return [(call.args[0].token, call.args[0].data['type']) for call in self.fcm_send.call_args_list]

    def quote_url(self, action=''):
        name = {'': 'quote-submit', 'accept': 'quote-accept', 'reject': 'quote-reject'}[action]
        return reverse(f'service_requests:{name}', kwargs={'request_id': REQ})


class AuthenticationTests(AppApiTestCase):

    def test_requires_token(self):
        response = self.api().post(self.quote_url(), {'quoted_price': 50000}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_invalid_and_revoked_tokens(self):
        for uid in ('invalid', 'revoked'):
            response = self.api(uid).post(self.quote_url(), {'quoted_price': 50000}, format='json')
            self.assertEqual(response.status_code, 401)

    def test_panel_jwt_is_not_accepted_on_app_endpoints(self):
        user = User.objects.create_user('admin', password='x')
        from rest_framework_simplejwt.tokens import AccessToken
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
        response = client.post(self.quote_url(), {'quoted_price': 50000}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_app_token_cannot_list_payments(self):
        self.assertEqual(self.api(CLIENT).get(reverse('payments:payment-list')).status_code, 403)


class QuoteTests(AppApiTestCase):

    def test_worker_quotes_and_request_is_accepted(self):
        response = self.api(WORKER).post(self.quote_url(), {'quoted_price': 85000}, format='json')

        self.assertEqual(response.status_code, 200)
        request = self.request_data()
        self.assertEqual(request['status'], 'accepted')
        self.assertEqual(request['quoted_price'], 85000)
        self.assertEqual(request['quote_status'], 'quoted')
        self.assertIn(('fcm-client', 'quote_received'), self.sent_notifications())

    def test_only_assigned_worker_can_quote(self):
        for uid in (OTHER, CLIENT):
            response = self.api(uid).post(self.quote_url(), {'quoted_price': 85000}, format='json')
            self.assertEqual(response.status_code, 403)
        self.assertNotIn('quoted_price', self.request_data())

    def test_price_must_be_integer_and_in_range(self):
        for price in (85000.5, '85000', True, 0, 500, 6000000):
            response = self.api(WORKER).post(self.quote_url(), {'quoted_price': price}, format='json')
            self.assertEqual(response.status_code, 400, price)
        self.assertNotIn('quoted_price', self.request_data())

    def test_range_per_service_type_from_system_config(self):
        SystemConfig.objects.create(key='quote_price_ranges',
                                    value=json.dumps({'Plomería': {'min': 30000, 'max': 200000}}))
        self.assertEqual(self.api(WORKER).post(self.quote_url(), {'quoted_price': 250000}, format='json').status_code, 400)
        self.assertEqual(self.api(WORKER).post(self.quote_url(), {'quoted_price': 150000}, format='json').status_code, 200)

        limits = self.api(WORKER).get(reverse('service_requests:quote-limits'), {'service_type': 'Plomería'}).json()
        self.assertEqual(limits['data'], {'min_price': 30000, 'max_price': 200000, 'currency': 'COP'})

    def test_client_accepts_and_quote_becomes_immutable(self):
        self.api(WORKER).post(self.quote_url(), {'quoted_price': 85000}, format='json')

        self.assertEqual(self.api(WORKER).post(self.quote_url('accept')).status_code, 403)
        self.assertEqual(self.api(CLIENT).post(self.quote_url('accept')).status_code, 200)
        self.assertEqual(self.request_data()['quote_status'], 'accepted')
        self.assertIn(('fcm-worker', 'quote_accepted'), self.sent_notifications())

        self.assertEqual(self.api(CLIENT).post(self.quote_url('accept')).status_code, 409)
        self.assertEqual(self.api(WORKER).post(self.quote_url(), {'quoted_price': 1000}, format='json').status_code, 409)
        self.assertEqual(self.request_data()['quoted_price'], 85000)

    def test_reject_and_requote(self):
        self.api(WORKER).post(self.quote_url(), {'quoted_price': 85000}, format='json')
        response = self.api(CLIENT).post(self.quote_url('reject'), {'reason': 'Muy caro'}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.request_data()['quote_status'], 'rejected')
        self.assertEqual(self.request_data()['quote_rejection_reason'], 'Muy caro')

        self.api(WORKER).post(self.quote_url(), {'quoted_price': 70000}, format='json')
        request = self.request_data()
        self.assertEqual((request['quote_status'], request['quoted_price']), ('quoted', 70000))
        self.assertNotIn('quote_rejection_reason', request)

    def test_cannot_quote_cancelled_request(self):
        self.set_request(status='cancelled')
        self.assertEqual(self.api(WORKER).post(self.quote_url(), {'quoted_price': 85000}, format='json').status_code, 409)

    def test_invalid_firebase_key_and_unknown_request(self):
        url = reverse('service_requests:quote-submit', kwargs={'request_id': 'a.b'})
        self.assertEqual(self.api(WORKER).post(url, {'quoted_price': 85000}, format='json').status_code, 400)
        url = reverse('service_requests:quote-submit', kwargs={'request_id': 'no-existe'})
        self.assertEqual(self.api(WORKER).post(url, {'quoted_price': 85000}, format='json').status_code, 404)


class PaymentApiTests(AppApiTestCase):

    def setUp(self):
        super().setUp()
        self.set_request(status='completed', quoted_price=85000, quote_status='accepted')

    def start(self, uid=CLIENT, **body):
        payload = {'service_request_id': REQ}
        payload.update(body)
        return self.api(uid).post(reverse('payments:payment-list'), payload, format='json')

    def test_amount_comes_from_accepted_quote(self):
        response = self.start(amount_in_cents=100, amount=1)

        self.assertEqual(response.status_code, 201)
        data = response.json()['data']
        self.assertEqual(data['amount_in_cents'], 8500000)
        self.assertEqual(data['amount_cop'], 85000)
        self.assertIn('/api/payments/mock-checkout/', data['checkout_url'])
        self.assertIn('redirect-url=adsapp', data['checkout_url'])

        payment = Payment.objects.get()
        self.assertEqual((payment.client_uid, payment.worker_uid), (CLIENT, WORKER))
        self.assertEqual(self.request_data()['payment_status'], 'pending')

    def test_only_owner_client_can_pay(self):
        for uid in (WORKER, OTHER):
            self.assertEqual(self.start(uid).status_code, 403)
        self.assertFalse(Payment.objects.exists())

    def test_request_must_be_payable(self):
        for values in ({'status': 'in_progress'}, {'quote_status': 'quoted'}, {'quoted_price': 850.5}):
            self.set_request(status='completed', quoted_price=85000, quote_status='accepted')
            self.set_request(**values)
            self.assertEqual(self.start().status_code, 409, values)
        self.assertFalse(Payment.objects.exists())

    def test_rejects_external_redirect(self):
        self.assertEqual(self.start(redirect_url='https://evil.example/x').status_code, 400)

    def test_second_request_reuses_pending_payment(self):
        first = self.start().json()['data']
        response = self.start()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['reference'], first['reference'])
        self.assertEqual(Payment.objects.count(), 1)

    def test_expired_pending_payment_is_closed_and_replaced(self):
        first = self.start().json()['data']
        Payment.objects.filter(reference=first['reference']).update(
            created_at=timezone.now() - timedelta(minutes=31))

        response = self.start()

        self.assertEqual(response.status_code, 201)
        self.assertNotEqual(response.json()['data']['reference'], first['reference'])
        old = Payment.objects.get(reference=first['reference'])
        self.assertEqual(old.status, Payment.STATUS_ERROR)
        self.assertTrue(old.events.filter(event_type='local.expired').exists())

    def test_paid_request_cannot_be_paid_again(self):
        self.start()
        Payment.objects.update(status=Payment.STATUS_APPROVED)
        self.assertEqual(self.start().status_code, 409)

    def test_end_to_end_with_mock_checkout_and_notification(self):
        reference = self.start().json()['data']['reference']
        payment = Payment.objects.get(reference=reference)
        event = get_gateway().build_event(reference, 'mock-1-1', 'APPROVED', payment.amount_in_cents, 'COP')

        response = APIClient().post(reverse('payments:webhook'), event, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.request_data()['payment_status'], 'approved')
        self.assertIn(('fcm-worker', 'payment_approved'), self.sent_notifications())

    def test_detail_visibility(self):
        reference = self.start().json()['data']['reference']
        url = reverse('payments:payment-detail', kwargs={'reference': reference})

        self.assertEqual(self.api(CLIENT).get(url).status_code, 200)
        self.assertEqual(self.api(WORKER).get(url).status_code, 200)
        self.assertNotIn('events', self.api(CLIENT).get(url).json()['data'])
        self.assertEqual(self.api(OTHER).get(url).status_code, 404)
        self.assertEqual(self.api().get(url).status_code, 401)

        panel = APIClient()
        panel.force_authenticate(User.objects.create_user('admin', password='x'))
        data = panel.get(url).json()['data']
        self.assertIn('events', data)
        self.assertEqual(data['client_uid'], CLIENT)

    def test_panel_list_with_filters(self):
        self.start()
        panel = APIClient()
        panel.force_authenticate(User.objects.create_user('admin', password='x'))

        response = panel.get(reverse('payments:payment-list'), {'status': 'pending'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(panel.get(reverse('payments:payment-list'), {'status': 'APPROVED'}).json()['count'], 0)


class RatingTests(AppApiTestCase):

    def setUp(self):
        super().setUp()
        self.set_request(status='completed', quoted_price=85000, quote_status='accepted')
        self.url = reverse('service_requests:rating', kwargs={'request_id': REQ})

    def rate(self, uid=CLIENT, rating=5, comment='Excelente'):
        return self.api(uid).post(self.url, {'rating': rating, 'comment': comment}, format='json')

    def test_requires_payment(self):
        self.assertEqual(self.rate().status_code, 409)
        self.assertFalse(self.request_data()['is_rated'])

    def test_rating_updates_request_and_worker_average(self):
        self.set_request(payment_status='approved')
        response = self.rate()

        self.assertEqual(response.status_code, 200)
        request = self.request_data()
        self.assertTrue(request['is_rated'])
        self.assertEqual(request['client_rating'], 5)
        worker = self.fb.get_data(f"User/Trabajadores/{WORKER}")
        self.assertEqual(worker['totalRatings'], 3)
        self.assertEqual(worker['rating'], 4.33)

    def test_rate_only_once_only_by_client_and_valid_value(self):
        self.set_request(payment_status='approved')
        self.assertEqual(self.rate(WORKER).status_code, 403)
        for value in (0, 6, 4.5):
            self.assertEqual(self.rate(rating=value).status_code, 400)
        self.assertEqual(self.rate().status_code, 200)
        self.assertEqual(self.rate(rating=1).status_code, 409)
        self.assertEqual(self.fb.get_data(f"User/Trabajadores/{WORKER}/totalRatings"), 3)

    def test_rating_is_throttled(self):
        statuses = [self.rate().status_code for _ in range(11)]
        self.assertEqual(statuses[-1], 429)


class NotificationApiTests(AppApiTestCase):

    def notify(self, uid, notification_type):
        return self.api(uid).post(reverse('service_requests:notifications'),
                                  {'request_id': REQ, 'type': notification_type}, format='json')

    def test_client_notifies_worker_of_new_request(self):
        response = self.notify(CLIENT, 'new_request')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['data']['sent'])
        message = self.fcm_send.call_args.args[0]
        self.assertEqual(message.token, 'fcm-worker')
        self.assertEqual(message.data['title'], 'Nueva Solicitud de Servicio')
        self.assertEqual(message.data['requestId'], REQ)

    def test_sender_role_and_status_are_checked(self):
        self.assertEqual(self.notify(WORKER, 'new_request').status_code, 403)
        self.assertEqual(self.notify(OTHER, 'new_request').status_code, 403)
        self.assertEqual(self.notify(WORKER, 'status_change').status_code, 409)
        self.assertEqual(self.notify(CLIENT, 'payment_approved').status_code, 400)
        self.fcm_send.assert_not_called()

    def test_status_change_uses_current_status(self):
        self.set_request(status='on_the_way')
        self.notify(WORKER, 'status_change')
        message = self.fcm_send.call_args.args[0]
        self.assertEqual(message.token, 'fcm-client')
        self.assertEqual(message.data['status'], 'on_the_way')

    def test_stale_token_is_removed(self):
        from firebase_admin import messaging
        self.fcm_send.side_effect = messaging.UnregisteredError('Requested entity was not found.')

        response = self.notify(CLIENT, 'new_request')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['data']['sent'])
        self.assertIsNone(self.fb.get_data(f"Tokens/{WORKER}"))
        self.assertIsNotNone(self.fb.get_data(f"Tokens/{CLIENT}"))

    def test_missing_token_is_not_an_error(self):
        self.fb.set_data(f"Tokens/{WORKER}", None)
        response = self.notify(CLIENT, 'new_request')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['data']['sent'])
