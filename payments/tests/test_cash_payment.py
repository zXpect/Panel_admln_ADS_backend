from unittest import mock

from django.urls import reverse

from ..models import Payment
from .test_api import CLIENT, OTHER, REQ, WORKER, AppApiTestCase


class CashPaymentTests(AppApiTestCase):
    """Método de pago y pago en efectivo (D10, D11)."""

    def setUp(self):
        super().setUp()
        self.set_request(status='accepted', quoted_price=85000, quote_status='quoted')

    def url(self, name):
        return reverse(f'service_requests:{name}', kwargs={'request_id': REQ})

    def accept(self, **body):
        return self.api(CLIENT).post(self.url('quote-accept'), body, format='json')

    def set_method(self, method, uid=CLIENT):
        return self.api(uid).post(self.url('payment-method'), {'payment_method': method}, format='json')

    def cash_received(self, uid=WORKER):
        return self.api(uid).post(self.url('cash-received'), {}, format='json')

    def test_accept_quote_stores_payment_method(self):
        response = self.accept(payment_method='cash')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['payment_method'], 'cash')
        self.assertEqual(self.request_data()['payment_method'], 'cash')

    def test_accept_quote_without_method_keeps_old_app_working(self):
        self.assertEqual(self.accept().status_code, 200)
        self.assertNotIn('payment_method', self.request_data())
        self.assertEqual(self.accept(payment_method='bitcoin').status_code, 400)

    def test_client_changes_method_until_service_ends(self):
        self.accept(payment_method='digital')
        self.set_request(status='in_progress')
        self.assertEqual(self.set_method('cash').status_code, 200)
        self.assertEqual(self.request_data()['payment_method'], 'cash')

        self.assertEqual(self.set_method('digital', uid=WORKER).status_code, 403)
        self.assertEqual(self.set_method('digital', uid=OTHER).status_code, 403)
        self.set_request(status='completed')
        self.assertEqual(self.set_method('digital').status_code, 409)

    def test_method_requires_accepted_quote(self):
        self.assertEqual(self.set_method('cash').status_code, 409)

    def test_worker_registers_cash_and_client_is_notified(self):
        self.accept(payment_method='cash')
        self.set_request(status='completed')

        response = self.cash_received()

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        request = self.request_data()
        self.assertEqual(request['payment_status'], 'approved')
        self.assertEqual(request['payment_reference'], data['payment_reference'])
        self.assertEqual(request['cash_received_at'], data['cash_received_at'])
        payment = Payment.objects.get(reference=data['payment_reference'])
        self.assertEqual((payment.gateway, payment.status, payment.amount_in_cents, payment.client_uid),
                         ('cash', 'APPROVED', 8500000, CLIENT))
        self.assertIn(('fcm-client', 'cash_received'), self.sent_notifications())
        history = list(self.fb.get_data(f"notifications/{CLIENT}").values())
        self.assertIn('$85.000', history[-1]['body'])
        # Solo una vez
        self.assertEqual(self.cash_received().status_code, 409)

    def test_cash_received_checks(self):
        self.accept(payment_method='digital')
        self.set_request(status='completed')
        self.assertEqual(self.cash_received().status_code, 409)  # no es efectivo

        self.set_request(payment_method='cash', status='in_progress')
        self.assertEqual(self.cash_received().status_code, 409)  # no ha terminado

        self.set_request(status='completed')
        self.assertEqual(self.cash_received(uid=CLIENT).status_code, 403)
        self.assertEqual(self.cash_received().status_code, 200)

    def test_firebase_failure_rolls_back_cash_payment(self):
        self.accept(payment_method='cash')
        self.set_request(status='completed')
        with mock.patch.object(self.fb, 'get_database_reference', side_effect=Exception('down')):
            self.assertEqual(self.cash_received().status_code, 500)
        self.assertFalse(Payment.objects.exists())

    def test_rating_allowed_after_cash_received(self):
        self.accept(payment_method='cash')
        self.set_request(status='completed')
        rate = lambda: self.api(CLIENT).post(self.url('rating'), {'rating': 5}, format='json')  # noqa: E731
        self.assertEqual(rate().status_code, 409)
        self.cash_received()
        self.assertEqual(rate().status_code, 200)

    def test_cash_request_cannot_be_paid_with_wompi(self):
        self.accept(payment_method='cash')
        self.set_request(status='completed')
        response = self.api(CLIENT).post(reverse('payments:payment-list'),
                                         {'service_request_id': REQ}, format='json')
        self.assertEqual(response.status_code, 409)

        self.cash_received()
        self.set_request(payment_method='digital')
        response = self.api(CLIENT).post(reverse('payments:payment-list'),
                                         {'service_request_id': REQ}, format='json')
        self.assertEqual(response.status_code, 409)
