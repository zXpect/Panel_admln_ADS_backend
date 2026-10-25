import time

from django.urls import reverse

from worker_verification.models import SystemConfig

from .test_api import CLIENT, OTHER, REQ, WORKER, AppApiTestCase

HOUR_MS = 60 * 60 * 1000
DAY_MS = 24 * HOUR_MS

# Referencia congelada de destapar desagüe + reparar grifo (68.000 – 153.000)
PRICED_REFERENCE = {
    'min_cop': 68000, 'max_cop': 153000, 'regional_factor_pct': -15, 'min_visit_fee_cop': 25500,
    'has_unpriced_items': False, 'items': [],
}


def in_hours(hours):
    return int(time.time() * 1000) + hours * HOUR_MS


class RequestFlowTestCase(AppApiTestCase):

    def url(self, name, request_id=REQ):
        return reverse(f'service_requests:{name}', kwargs={'request_id': request_id})

    def quote(self, uid=WORKER, price=100000, request_id=REQ, **overrides):
        data = {'quoted_price': price, 'scheduled_at': in_hours(24), 'estimated_duration_min': 90}
        data.update(overrides)
        return self.api(uid).post(self.url('quote-submit', request_id), data, format='json')


class QuoteTests(RequestFlowTestCase):

    def setUp(self):
        super().setUp()
        self.set_request(quote_reference=PRICED_REFERENCE)

    def test_quote_within_range_needs_no_reason_and_stores_schedule(self):
        scheduled_at = in_hours(30)
        response = self.quote(price=100000, scheduled_at=scheduled_at, estimated_duration_min=120,
                              adjustment_reason_code='materiales')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data'], {
            'request_id': REQ, 'status': 'accepted', 'quoted_price': 100000, 'quote_status': 'quoted'})

        request = self.request_data()
        self.assertFalse(request['quote_is_adjusted'])
        # Sin ajuste no se guarda el motivo aunque llegue
        self.assertNotIn('quote_adjustment_reason_code', request)
        self.assertNotIn('quote_adjustment_reason_text', request)
        self.assertEqual((request['scheduled_at'], request['estimated_duration_min']), (scheduled_at, 120))
        self.assertIn(('fcm-client', 'quote_received'), self.sent_notifications())

    def test_range_limits_are_inclusive(self):
        self.assertEqual(self.quote(price=68000).status_code, 200)
        self.assertFalse(self.request_data()['quote_is_adjusted'])
        self.assertEqual(self.quote(price=153000).status_code, 200)
        self.assertFalse(self.request_data()['quote_is_adjusted'])

    def test_adjusted_price_requires_reason(self):
        for price in (60000, 160000):
            with self.subTest(price=price):
                response = self.quote(price=price)
                self.assertEqual(response.status_code, 400)
        self.assertNotIn('quoted_price', self.request_data())

        self.assertEqual(self.quote(price=160000, adjustment_reason_code='dificultad').status_code, 200)
        request = self.request_data()
        self.assertTrue(request['quote_is_adjusted'])
        self.assertEqual(request['quote_adjustment_reason_code'], 'dificultad')
        self.assertNotIn('quote_adjustment_reason_text', request)

    def test_any_reason_keeps_an_optional_comment(self):
        """El cliente ve el detalle además de la etiqueta del motivo (MEJ-01)."""
        self.quote(price=160000, adjustment_reason_code='materiales',
                   adjustment_reason_text='  Hace falta cable adicional ')
        request = self.request_data()
        self.assertEqual((request['quote_adjustment_reason_code'], request['quote_adjustment_reason_text']),
                         ('materiales', 'Hace falta cable adicional'))
        # Solo espacios: sin comentario
        self.quote(price=160000, adjustment_reason_code='tiempo', adjustment_reason_text='   ')
        self.assertNotIn('quote_adjustment_reason_text', self.request_data())

    def test_other_reason_requires_text(self):
        response = self.quote(price=160000, adjustment_reason_code='otro')
        self.assertEqual(response.status_code, 400)
        self.assertIn('adjustment_reason_text', response.json()['errors'])

        response = self.quote(price=160000, adjustment_reason_code='otro',
                              adjustment_reason_text='Hay que romper pared para llegar al tubo')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.request_data()['quote_adjustment_reason_text'], 'Hay que romper pared para llegar al tubo')

    def test_invalid_reason_code_and_long_text(self):
        self.assertEqual(self.quote(price=160000, adjustment_reason_code='capricho').status_code, 400)
        self.assertEqual(self.quote(price=160000, adjustment_reason_code='otro',
                                    adjustment_reason_text='x' * 301).status_code, 400)

    def test_unpriced_items_always_require_reason(self):
        self.set_request(quote_reference={**PRICED_REFERENCE, 'has_unpriced_items': True})
        self.assertEqual(self.quote(price=100000).status_code, 400)
        self.assertEqual(self.quote(price=100000, adjustment_reason_code='tiempo').status_code, 200)
        self.assertTrue(self.request_data()['quote_is_adjusted'])

    def test_old_request_without_reference_still_works_with_reason(self):
        self.fb.set_data(f"requests/{REQ}/quote_reference", None)
        self.assertEqual(self.quote(price=100000).status_code, 400)
        self.assertEqual(self.quote(price=100000, adjustment_reason_code='materiales').status_code, 200)
        self.assertTrue(self.request_data()['quote_is_adjusted'])

    def test_price_floor_ceiling_and_type(self):
        self.set_request(quote_reference={**PRICED_REFERENCE, 'has_unpriced_items': True})
        for price in (25499, 5000001, 85000.5, '85000', True, 0):
            with self.subTest(price=price):
                self.assertEqual(self.quote(price=price, adjustment_reason_code='materiales').status_code, 400)
        self.assertEqual(self.quote(price=25500, adjustment_reason_code='materiales').status_code, 200)

        SystemConfig.objects.filter(key='quote_min_visit_fee_cop').update(value='30000')
        self.assertEqual(self.quote(price=25500, adjustment_reason_code='materiales').status_code, 400)

    def test_schedule_must_be_future_within_30_days_with_valid_duration(self):
        cases = {
            'pasado': {'scheduled_at': in_hours(-1)},
            'a más de 30 días': {'scheduled_at': in_hours(31 * 24)},
            'sin fecha': {'scheduled_at': None},
            'duración corta': {'estimated_duration_min': 10},
            'duración larga': {'estimated_duration_min': 721},
            'sin duración': {'estimated_duration_min': None},
        }
        for name, overrides in cases.items():
            with self.subTest(name):
                data = {key: value for key, value in overrides.items() if value is not None}
                response = self.api(WORKER).post(self.url('quote-submit'), {
                    'quoted_price': 100000, 'scheduled_at': in_hours(24), 'estimated_duration_min': 90,
                    **data,
                    **{key: None for key, value in overrides.items() if value is None},
                }, format='json')
                self.assertEqual(response.status_code, 400)
        self.assertNotIn('quoted_price', self.request_data())

    def test_only_assigned_worker_can_quote(self):
        for uid in (OTHER, CLIENT):
            self.assertEqual(self.quote(uid=uid).status_code, 403)
        self.assertNotIn('quoted_price', self.request_data())

    def test_client_accepts_and_quote_becomes_immutable(self):
        self.quote(price=85000)
        self.assertEqual(self.api(WORKER).post(self.url('quote-accept')).status_code, 403)
        self.assertEqual(self.api(CLIENT).post(self.url('quote-accept')).status_code, 200)
        self.assertEqual(self.request_data()['quote_status'], 'accepted')
        self.assertIn(('fcm-worker', 'quote_accepted'), self.sent_notifications())

        self.assertEqual(self.api(CLIENT).post(self.url('quote-accept')).status_code, 409)
        self.assertEqual(self.quote(price=90000).status_code, 409)
        self.assertEqual(self.request_data()['quoted_price'], 85000)

    def test_reject_and_requote_clears_previous_reason(self):
        self.quote(price=160000, adjustment_reason_code='otro', adjustment_reason_text='Tubería oculta')
        response = self.api(CLIENT).post(self.url('quote-reject'), {'reason': 'Muy caro'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.request_data()['quote_rejection_reason'], 'Muy caro')

        self.assertEqual(self.quote(price=70000).status_code, 200)
        request = self.request_data()
        self.assertEqual((request['quote_status'], request['quoted_price']), ('quoted', 70000))
        self.assertFalse(request['quote_is_adjusted'])
        for field in ('quote_rejection_reason', 'quote_adjustment_reason_code', 'quote_adjustment_reason_text'):
            self.assertNotIn(field, request)

    def test_cannot_quote_cancelled_request(self):
        self.set_request(status='cancelled')
        self.assertEqual(self.quote().status_code, 409)

    def test_invalid_firebase_key_and_unknown_request(self):
        self.assertEqual(self.quote(request_id='a.b').status_code, 400)
        self.assertEqual(self.quote(request_id='no-existe').status_code, 404)

    def test_quote_limits_come_from_min_fee_and_max_price(self):
        limits = self.api(WORKER).get(reverse('service_requests:quote-limits')).json()
        self.assertEqual(limits['data'], {'min_price': 25500, 'max_price': 5000000, 'currency': 'COP'})


class ScheduleTests(RequestFlowTestCase):

    def setUp(self):
        super().setUp()
        self.set_request(quote_reference=PRICED_REFERENCE)
        self.quote(price=100000)
        self.fcm_send.reset_mock()

    def schedule(self, uid=WORKER, **overrides):
        data = {'scheduled_at': in_hours(48), 'estimated_duration_min': 60}
        data.update(overrides)
        return self.api(uid).post(self.url('schedule'), data, format='json')

    def test_worker_reschedules_and_client_is_notified(self):
        scheduled_at = in_hours(48)
        response = self.schedule(scheduled_at=scheduled_at)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data'], {
            'request_id': REQ, 'scheduled_at': scheduled_at, 'estimated_duration_min': 60, 'reschedule_count': 1})

        request = self.request_data()
        self.assertEqual(request['reschedule_count'], 1)
        self.assertIn('rescheduled_at', request)
        self.assertEqual(self.sent_notifications(), [('fcm-client', 'request_rescheduled')])

        self.assertEqual(self.schedule().json()['data']['reschedule_count'], 2)

    def test_also_after_quote_is_accepted(self):
        self.api(CLIENT).post(self.url('quote-accept'))
        self.assertEqual(self.schedule().status_code, 200)

    def test_only_worker_and_only_in_accepted(self):
        self.assertEqual(self.schedule(uid=CLIENT).status_code, 403)
        self.assertEqual(self.schedule(uid=OTHER).status_code, 403)
        for status in ('pending', 'on_the_way', 'in_progress', 'completed', 'cancelled'):
            with self.subTest(status=status):
                self.set_request(status=status)
                self.assertEqual(self.schedule().status_code, 409)
        self.assertNotIn('reschedule_count', self.request_data())

    def test_invalid_schedule(self):
        self.assertEqual(self.schedule(scheduled_at=in_hours(-2)).status_code, 400)
        self.assertEqual(self.schedule(scheduled_at=in_hours(24 * 31)).status_code, 400)
        self.assertEqual(self.schedule(estimated_duration_min=14).status_code, 400)


class CancelTests(RequestFlowTestCase):

    def cancel(self, uid=CLIENT, reason_code='horario', reason_text=''):
        return self.api(uid).post(self.url('cancel'), {'reason_code': reason_code, 'reason_text': reason_text},
                                  format='json')

    def test_client_cancels_pending_request(self):
        response = self.cancel()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data'], {'request_id': REQ, 'status': 'cancelled', 'cancelled_by': 'client'})

        request = self.request_data()
        self.assertEqual((request['status'], request['cancelled_by'], request['cancellation_reason_code']),
                         ('cancelled', 'client', 'horario'))
        self.assertNotIn('cancellation_reason_text', request)
        self.assertIn('cancelled_at', request)
        self.assertEqual(self.sent_notifications(), [('fcm-worker', 'request_cancelled')])

    def test_worker_cancels_accepted_request_even_with_accepted_quote(self):
        self.set_request(status='accepted', quoted_price=90000, quote_status='accepted')
        response = self.cancel(uid=WORKER, reason_code='otro', reason_text='Se me dañó la moto')
        self.assertEqual(response.status_code, 200)
        request = self.request_data()
        self.assertEqual((request['cancelled_by'], request['cancellation_reason_text']), ('worker', 'Se me dañó la moto'))
        self.assertEqual(self.sent_notifications(), [('fcm-client', 'request_cancelled')])

    def test_cancel_push_carries_reason(self):
        """El push dice el motivo: la etiqueta de la lista o el texto con «otro» (DEF-27)."""
        self.set_request(client_name='Emmanuel', worker_name='Breider López')
        self.cancel(reason_code='horario')
        self.assertEqual(self.fcm_send.call_args.args[0].data['body'],
                         'Emmanuel canceló la solicitud. Motivo: Por el horario')

        self.set_request(status='pending')
        self.cancel(uid=WORKER, reason_code='otro', reason_text='Se me dañó la moto')
        self.assertEqual(self.fcm_send.call_args.args[0].data['body'],
                         'Breider López canceló la solicitud. Motivo: Se me dañó la moto')

    def test_started_service_answers_409_pqr(self):
        for status in ('on_the_way', 'in_progress', 'completed'):
            with self.subTest(status=status):
                self.set_request(status=status)
                response = self.cancel()
                self.assertEqual(response.status_code, 409)
                self.assertIn('PQR', response.json()['error'])
        self.assertEqual(self.request_data()['status'], 'completed')

    def test_closed_request_cannot_be_cancelled_again(self):
        for status in ('cancelled', 'rejected'):
            self.set_request(status=status)
            self.assertEqual(self.cancel().status_code, 409)

    def test_reason_must_match_role_and_other_requires_text(self):
        self.assertEqual(self.cancel(uid=CLIENT, reason_code='fuera_de_zona').status_code, 400)
        self.assertEqual(self.cancel(uid=WORKER, reason_code='precio').status_code, 400)
        self.assertEqual(self.cancel(reason_code='inventado').status_code, 400)
        response = self.cancel(reason_code='otro')
        self.assertEqual(response.status_code, 400)
        self.assertIn('reason_text', response.json()['errors'])
        self.assertEqual(self.request_data()['status'], 'pending')

    def test_outsider_cannot_cancel(self):
        self.assertEqual(self.cancel(uid=OTHER).status_code, 403)
        self.assertEqual(self.request_data()['status'], 'pending')

    def test_unknown_request(self):
        response = self.api(CLIENT).post(self.url('cancel', 'no-existe'), {'reason_code': 'horario'}, format='json')
        self.assertEqual(response.status_code, 404)
