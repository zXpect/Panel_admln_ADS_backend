from datetime import date, datetime, timezone

from django.contrib.auth.models import User
from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework.test import APIClient

from payments.tests.test_api import CLIENT, OTHER, REQ, WORKER, AppApiTestCase

from ..models import PQR
from ..services.business_days import add_business_days, colombian_holidays, easter_sunday


class BusinessDaysTests(SimpleTestCase):

    def test_easter(self):
        self.assertEqual(easter_sunday(2026), date(2026, 4, 5))
        self.assertEqual(easter_sunday(2027), date(2027, 3, 28))

    def test_colombian_holidays_2026(self):
        expected = {
            date(2026, 1, 1), date(2026, 1, 12), date(2026, 3, 23), date(2026, 4, 2), date(2026, 4, 3),
            date(2026, 5, 1), date(2026, 5, 18), date(2026, 6, 8), date(2026, 6, 15), date(2026, 6, 29),
            date(2026, 7, 20), date(2026, 8, 7), date(2026, 8, 17), date(2026, 10, 12), date(2026, 11, 2),
            date(2026, 11, 16), date(2026, 12, 8), date(2026, 12, 25),
        }
        self.assertEqual(colombian_holidays(2026), expected)

    def test_example_from_api_spec(self):
        # 16/10/2026 (viernes) + 15 días hábiles, saltando el festivo del 2/11 → 9/11
        created = datetime(2026, 10, 16, 17, 30, tzinfo=timezone.utc)
        self.assertEqual(add_business_days(created, 15), datetime(2026, 11, 9, 17, 30, tzinfo=timezone.utc))

    def test_counts_in_colombian_time(self):
        # Sábado 02:00 UTC es viernes 21:00 en Colombia: cuenta desde el viernes
        created = datetime(2026, 10, 24, 2, 0, tzinfo=timezone.utc)
        self.assertEqual(add_business_days(created, 1).date(), date(2026, 10, 27))  # lunes 26, 21:00 COT


class PqrApiTests(AppApiTestCase):

    def setUp(self):
        super().setUp()
        self.panel = APIClient()
        self.admin = User.objects.create_user('admin.ads', password='x')
        self.panel.force_authenticate(self.admin)

    def create(self, uid=CLIENT, **overrides):
        body = {'service_request_id': REQ, 'type': 'reclamo', 'description': 'El trabajador no llegó a la hora'}
        body.update(overrides)
        return self.api(uid).post(reverse('pqr:pqr-list'), body, format='json')

    def answer(self, pqr_id, **body):
        return self.panel.patch(reverse('pqr:pqr-detail', kwargs={'pk': pqr_id}), body, format='json')

    def test_participants_create_with_role_and_due_date(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        data = response.json()['data']
        self.assertEqual((data['author_role'], data['status'], data['response']), ('client', 'abierta', None))
        pqr = PQR.objects.get()
        # due_at se calcula un instante antes de que se guarde created_at
        self.assertLess(abs((pqr.due_at - add_business_days(pqr.created_at, 15)).total_seconds()), 1)

        self.assertEqual(self.create(uid=WORKER, type='peticion').json()['data']['author_role'], 'worker')

    def test_create_validation(self):
        self.assertEqual(self.create(uid=OTHER).status_code, 403)
        self.assertEqual(self.create(service_request_id='no-existe').status_code, 404)
        self.assertEqual(self.create(type='sugerencia').status_code, 400)
        self.assertEqual(self.create(description='   ').status_code, 400)
        self.assertEqual(self.create(service_request_id='a/b').status_code, 400)
        self.assertEqual(self.panel.post(reverse('pqr:pqr-list'), {}, format='json').status_code, 403)
        self.assertFalse(PQR.objects.exists())

    def test_app_sees_only_own_pqrs(self):
        own = self.create().json()['data']['id']
        other = self.create(uid=WORKER).json()['data']['id']

        listing = self.api(CLIENT).get(reverse('pqr:pqr-list')).json()
        self.assertEqual([item['id'] for item in listing['data']], [own])
        self.assertEqual(self.api(CLIENT).get(reverse('pqr:pqr-detail', kwargs={'pk': other})).status_code, 404)
        self.assertEqual(self.api(CLIENT).get(reverse('pqr:pqr-detail', kwargs={'pk': own})).status_code, 200)

        panel_listing = self.panel.get(reverse('pqr:pqr-list'), {'status': 'abierta'}).json()
        self.assertEqual(panel_listing['count'], 2)
        self.assertIn('is_overdue', panel_listing['data'][0])

    def test_panel_answers_and_closes(self):
        pqr_id = self.create().json()['data']['id']

        response = self.answer(pqr_id, status='en_tramite', response='Estamos revisando el caso con el trabajador')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['responded_by'], 'admin.ads')
        self.assertIn(('fcm-client', 'pqr_answered'), self.sent_notifications())
        history = list(self.fb.get_data(f"notifications/{CLIENT}").values())
        self.assertEqual((history[-1]['type'], history[-1]['request_id']), ('pqr_answered', REQ))

        response = self.answer(pqr_id, status='cerrada')
        self.assertEqual(response.status_code, 200)
        pqr = PQR.objects.get()
        self.assertEqual(pqr.status, 'cerrada')
        self.assertIsNotNone(pqr.closed_at)
        # Cerrar sin respuesta nueva no repite el aviso
        self.assertEqual(self.sent_notifications().count(('fcm-client', 'pqr_answered')), 1)

        self.assertEqual(self.answer(pqr_id, status='en_tramite').status_code, 409)

    def test_closing_requires_response(self):
        pqr_id = self.create().json()['data']['id']
        self.assertEqual(self.answer(pqr_id, status='cerrada').status_code, 400)
        self.assertEqual(self.answer(pqr_id, status='abierta').status_code, 400)
        self.assertEqual(self.answer(9999, status='en_tramite').status_code, 404)
        self.assertEqual(PQR.objects.get().status, 'abierta')

    def test_app_cannot_answer(self):
        pqr_id = self.create().json()['data']['id']
        response = self.api(CLIENT).patch(reverse('pqr:pqr-detail', kwargs={'pk': pqr_id}),
                                          {'status': 'cerrada', 'response': 'x'}, format='json')
        self.assertEqual(response.status_code, 403)
