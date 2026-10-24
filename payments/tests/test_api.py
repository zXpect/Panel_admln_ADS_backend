from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

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

    def test_panel_list_gateway_date_filters_and_summary(self):
        Payment.objects.create(reference='ADS-CASH', service_request_id='req-9', client_uid=CLIENT,
                               worker_uid=WORKER, amount_in_cents=5000000, status=Payment.STATUS_APPROVED,
                               gateway=Payment.GATEWAY_CASH)
        Payment.objects.create(reference='ADS-MOCK', service_request_id='req-8', client_uid=CLIENT,
                               worker_uid=WORKER, amount_in_cents=8500000, status=Payment.STATUS_APPROVED,
                               gateway=Payment.GATEWAY_MOCK)
        panel = APIClient()
        panel.force_authenticate(User.objects.create_user('admin', password='x'))
        url = reverse('payments:payment-list')

        body = panel.get(url).json()
        self.assertEqual(body['summary'], {
            'approved_count': 2, 'approved_total_cop': 135000,
            'approved_by_gateway': {'cash': {'count': 1, 'total_cop': 50000},
                                    'mock': {'count': 1, 'total_cop': 85000}},
        })
        self.assertEqual(panel.get(url, {'gateway': 'cash'}).json()['count'], 1)
        # created_at__date se compara en la zona horaria del proyecto
        today = timezone.localdate().isoformat()
        self.assertEqual(panel.get(url, {'date_from': today, 'date_to': today}).json()['count'], 2)
        self.assertEqual(panel.get(url, {'date_from': '2099-01-01'}).json()['count'], 0)
        self.assertEqual(panel.get(url, {'date_from': '18/10/2026'}).status_code, 400)


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
        self.assertEqual(message.data['title'], 'Nueva solicitud de servicio')
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

    def test_status_change_names_the_worker(self):
        """Los avisos de estado nombran al técnico, como los demás (DEF-30)."""
        self.set_request(status='completed', worker_name='Breider López')
        self.notify(WORKER, 'status_change')
        message = self.fcm_send.call_args.args[0]
        self.assertEqual(message.data['title'], 'Trabajo completado')
        self.assertEqual(message.data['body'], 'Breider López terminó el trabajo. Paga y califica el servicio')

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
        # El historial se guarda aunque no haya push
        self.assertEqual(len(self.fb.get_data(f"notifications/{WORKER}")), 1)

    def test_notification_is_saved_to_recipient_history(self):
        self.notify(CLIENT, 'new_request')

        history = self.fb.get_data(f"notifications/{WORKER}")
        self.assertEqual(len(history), 1)
        entry = next(iter(history.values()))
        self.assertEqual(entry['title'], 'Nueva solicitud de servicio')
        self.assertEqual(entry['type'], 'new_request')
        self.assertEqual(entry['request_id'], REQ)
        self.assertFalse(entry['read'])
        self.assertIsInstance(entry['created_at'], int)
        self.assertIsNone(self.fb.get_data(f"notifications/{CLIENT}"))

    def test_push_carries_history_entry_id(self):
        self.notify(CLIENT, 'new_request')

        message = self.fcm_send.call_args.args[0]
        history = self.fb.get_data(f"notifications/{WORKER}")
        self.assertEqual(list(history), [message.data['notificationId']])
        # El historial no guarda su propia clave
        self.assertNotIn('notificationId', history[message.data['notificationId']])

    def test_history_failure_does_not_block_push(self):
        with mock.patch.object(self.fb, 'get_database_reference', side_effect=Exception('down')):
            response = self.notify(CLIENT, 'new_request')
        self.assertTrue(response.json()['data']['sent'])
        self.assertNotIn('notificationId', self.fcm_send.call_args.args[0].data)
