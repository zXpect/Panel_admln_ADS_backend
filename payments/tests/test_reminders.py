from io import StringIO
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from ..services.reminder_service import HOUR_MS, MINUTE_MS, reminder_service
from .test_api import CLIENT, WORKER, AppApiTestCase

NOW = 1_800_000_000_000


class ReminderServiceTests(AppApiTestCase):
    """Recordatorios de HU-17: servicio próximo, cotización sin responder y pago pendiente."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(reminder_service, 'firebase', self.fb)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_at(self, now=NOW):
        return reminder_service.run(now=now)

    def history(self, uid):
        return [entry['type'] for entry in (self.fb.get_data(f"notifications/{uid}") or {}).values()]

    def test_upcoming_service_reminds_both_once(self):
        self.set_request(status='accepted', quote_status='accepted', scheduled_at=NOW + 90 * MINUTE_MS,
                         address='Calle 1')

        self.assertEqual(self.run_at(), {'service': 1, 'quote': 0, 'payment': 0})
        self.assertEqual(sorted(self.sent_notifications()),
                         [('fcm-client', 'service_reminder'), ('fcm-worker', 'service_reminder')])
        self.assertEqual(self.request_data()['reminder_service_at'], NOW + 90 * MINUTE_MS)
        self.assertEqual(self.history(CLIENT), ['service_reminder'])

        # La siguiente ejecución no lo repite
        self.assertEqual(self.run_at(NOW + 30 * MINUTE_MS)['service'], 0)
        self.assertEqual(self.fcm_send.call_count, 2)

    def test_rescheduled_service_is_reminded_again(self):
        self.set_request(status='accepted', quote_status='accepted', scheduled_at=NOW + HOUR_MS,
                         reminder_service_at=NOW - 5 * HOUR_MS)
        self.assertEqual(self.run_at()['service'], 1)

    def test_service_outside_the_window_or_without_accepted_quote(self):
        cases = [
            dict(quote_status='accepted', scheduled_at=NOW + 3 * HOUR_MS),   # aún lejos
            dict(quote_status='accepted', scheduled_at=NOW - MINUTE_MS),     # ya pasó
            dict(quote_status='quoted', scheduled_at=NOW + HOUR_MS),         # sin aceptar
            dict(quote_status='accepted', scheduled_at=None),
        ]
        for values in cases:
            self.set_request(status='accepted', **values)
            self.assertEqual(self.run_at()['service'], 0, values)
        self.fcm_send.assert_not_called()

    def test_quote_without_answer_after_12_hours(self):
        self.set_request(status='accepted', quote_status='quoted', quoted_price=85000,
                         quoted_at=NOW - 11 * HOUR_MS)
        self.assertEqual(self.run_at()['quote'], 0)

        self.assertEqual(self.run_at(NOW + 2 * HOUR_MS)['quote'], 1)
        self.assertEqual(self.sent_notifications(), [('fcm-client', 'quote_pending')])
        body = self.fcm_send.call_args.args[0].data['body']
        self.assertIn('$85.000', body)
        self.assertEqual(self.run_at(NOW + 3 * HOUR_MS)['quote'], 0)

    def test_pending_payment_reminds_client_or_worker_for_cash(self):
        self.set_request(status='completed', completed_at=NOW - 2 * HOUR_MS, payment_status='pending',
                         quoted_price=50000)
        self.fb.set_data('requests/req-cash', {'client_id': CLIENT, 'worker_id': WORKER, 'status': 'completed',
                                               'completed_at': NOW - 2 * HOUR_MS, 'payment_method': 'cash'})
        self.fb.set_data('requests/req-paid', {'client_id': CLIENT, 'worker_id': WORKER, 'status': 'completed',
                                               'completed_at': NOW - 2 * HOUR_MS, 'payment_status': 'approved'})
        self.fb.set_data('requests/req-recent', {'client_id': CLIENT, 'worker_id': WORKER, 'status': 'completed',
                                                 'completed_at': NOW - 10 * MINUTE_MS})

        self.assertEqual(self.run_at()['payment'], 2)
        self.assertEqual(sorted(self.sent_notifications()),
                         [('fcm-client', 'payment_pending'), ('fcm-worker', 'payment_pending')])
        self.assertEqual(self.fb.get_data('requests/req-cash/reminder_payment_at'), NOW - 2 * HOUR_MS)
        self.assertIsNone(self.fb.get_data('requests/req-paid/reminder_payment_at'))
        self.assertEqual(self.run_at(NOW + MINUTE_MS)['payment'], 0)

    def test_other_states_are_ignored(self):
        for status in ('pending', 'on_the_way', 'in_progress', 'cancelled'):
            self.set_request(status=status, quote_status='accepted', scheduled_at=NOW + HOUR_MS,
                             completed_at=NOW - 5 * HOUR_MS)
            self.assertEqual(self.run_at(), {'service': 0, 'quote': 0, 'payment': 0}, status)

    def test_management_command(self):
        self.set_request(status='accepted', quote_status='quoted', quoted_at=1)
        out = StringIO()
        call_command('send_reminders', stdout=out)
        self.assertIn('Cotizaciones: 1', out.getvalue())
        self.assertEqual(self.request_data()['reminder_quote_at'], 1)


class RemindersEndpointTests(AppApiTestCase):
    """POST /api/internal/reminders/ con el secreto del programador externo."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(reminder_service, 'firebase', self.fb)
        patcher.start()
        self.addCleanup(patcher.stop)

    def call(self, token=None):
        client = APIClient()
        headers = {'HTTP_X_REMINDERS_TOKEN': token} if token is not None else {}
        return client.post(reverse('reminders-run'), **headers)

    @override_settings(REMINDERS_TOKEN='secreto-de-prueba')
    def test_valid_token_runs_the_reminders(self):
        self.set_request(status='accepted', quote_status='quoted', quoted_at=1)
        response = self.call('secreto-de-prueba')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data'], {'service': 0, 'quote': 1, 'payment': 0})

    @override_settings(REMINDERS_TOKEN='secreto-de-prueba')
    def test_wrong_or_missing_token(self):
        self.assertEqual(self.call('otro').status_code, 403)
        self.assertEqual(self.call().status_code, 403)
        self.fcm_send.assert_not_called()

    @override_settings(REMINDERS_TOKEN='')
    def test_without_configured_token_the_route_is_hidden(self):
        self.assertEqual(self.call('').status_code, 404)


class PanelLoginThrottleTests(AppApiTestCase):
    """El login del panel limita los intentos por IP (fuerza bruta)."""

    def test_eleventh_attempt_in_a_minute_is_refused(self):
        cache.clear()
        User.objects.create_user('admin', password='correcta')
        url = reverse('token_obtain_pair')
        codes = [APIClient().post(url, {'username': 'admin', 'password': 'mala'}, format='json').status_code
                 for _ in range(10)]
        self.assertEqual(set(codes), {401})
        response = APIClient().post(url, {'username': 'admin', 'password': 'correcta'}, format='json')
        self.assertEqual(response.status_code, 429)
