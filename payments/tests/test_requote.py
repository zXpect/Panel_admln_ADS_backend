from django.urls import reverse

from .test_api import CLIENT, OTHER, REQ, WORKER, AppApiTestCase


class RequoteTests(AppApiTestCase):
    """Re-cotización única durante el servicio (D7)."""

    def setUp(self):
        super().setUp()
        self.set_request(status='on_the_way', quoted_price=85000, quote_status='accepted')

    def url(self, name):
        return reverse(f'service_requests:{name}', kwargs={'request_id': REQ})

    def requote(self, uid=WORKER, price=120000, **overrides):
        data = {'price': price, 'reason_code': 'dificultad'}
        data.update(overrides)
        return self.api(uid).post(self.url('requote'), data, format='json')

    def answer(self, accept, uid=CLIENT):
        return self.api(uid).post(self.url('requote-accept' if accept else 'requote-reject'), {}, format='json')

    def test_worker_requotes_and_client_is_notified(self):
        response = self.requote()
        self.assertEqual(response.status_code, 200)
        requote = response.json()['data']['requote']
        self.assertEqual((requote['price'], requote['status'], requote['reason_code'], requote['reason_text']),
                         (120000, 'pending', 'dificultad', ''))
        self.assertIsInstance(requote['requested_at'], int)
        # El precio vigente no cambia hasta que el cliente acepta
        self.assertEqual(self.request_data()['quoted_price'], 85000)
        self.assertIn(('fcm-client', 'requote_received'), self.sent_notifications())

    def test_accept_changes_price(self):
        self.requote()
        response = self.answer(accept=True)
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['quoted_price'], 120000)
        self.assertEqual(data['requote']['status'], 'accepted')
        self.assertIsInstance(data['requote']['answered_at'], int)
        self.assertEqual(self.request_data()['quoted_price'], 120000)
        self.assertIn(('fcm-worker', 'requote_accepted'), self.sent_notifications())

    def test_reject_keeps_original_price(self):
        self.requote()
        response = self.answer(accept=False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.request_data()['quoted_price'], 85000)
        self.assertEqual(self.request_data()['requote']['status'], 'rejected')
        self.assertIn(('fcm-worker', 'requote_rejected'), self.sent_notifications())
        # Ya respondida
        self.assertEqual(self.answer(accept=True).status_code, 409)

    def test_only_one_requote_per_service(self):
        self.requote()
        self.answer(accept=False)
        self.assertEqual(self.requote(price=130000).status_code, 409)

    def test_status_and_role_checks(self):
        self.assertEqual(self.requote(uid=CLIENT).status_code, 403)
        self.assertEqual(self.requote(uid=OTHER).status_code, 403)
        for status in ('accepted', 'completed', 'cancelled'):
            with self.subTest(status=status):
                self.set_request(status=status)
                self.assertEqual(self.requote().status_code, 409)
        self.set_request(status='in_progress')
        self.assertEqual(self.requote().status_code, 200)
        self.assertEqual(self.answer(accept=True, uid=WORKER).status_code, 403)
        self.assertEqual(self.answer(accept=True, uid=OTHER).status_code, 403)

    def test_answer_without_requote(self):
        self.assertEqual(self.answer(accept=True).status_code, 409)

    def test_price_and_reason_validation(self):
        self.assertEqual(self.requote(price=85000).status_code, 400)        # igual al vigente
        self.assertEqual(self.requote(price=100).status_code, 400)          # bajo la tarifa mínima
        self.assertEqual(self.requote(price=120000.5).status_code, 400)
        self.assertEqual(self.requote(reason_code='capricho').status_code, 400)
        self.assertEqual(self.requote(reason_code='otro').status_code, 400)
        self.assertNotIn('requote', self.request_data())

        response = self.requote(reason_code='otro', reason_text='Hay que cambiar la tubería completa')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.request_data()['requote']['reason_text'], 'Hay que cambiar la tubería completa')

    def test_payment_uses_accepted_requote(self):
        self.requote()
        self.answer(accept=True)
        self.set_request(status='completed')
        response = self.api(CLIENT).post(reverse('payments:payment-list'),
                                         {'service_request_id': REQ}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['data']['amount_in_cents'], 12000000)
