from django.urls import reverse

from pricing.models import Task
from worker_verification.models import SystemConfig

from .test_api import CLIENT, OTHER, WORKER, AppApiTestCase

URL = reverse('service_requests:request-create')


def body(**overrides):
    data = {
        'worker_id': WORKER,
        'service_category': 'plomeria',
        'address': 'Calle 7 # 6-25, barrio Centro, Ubaté',
        'description': 'El lavaplatos no desagua y el grifo gotea',
        'lat': 5.3086,
        'lng': -73.8150,
        'task_items': [
            {'task': 'destapar-desague-sanitario', 'quantity': 1},
            {'task': 'reparar-grifo-valvula', 'quantity': 1},
        ],
    }
    data.update(overrides)
    return data


class ServiceRequestCreateTests(AppApiTestCase):

    def setUp(self):
        super().setUp()
        self.fb.update_data(f"User/Trabajadores/{WORKER}", {
            'lastName': 'Gómez',
            'phone': '3001112233',
            'categories': ['plomeria', 'electricidad'],
            'verificationStatus': {'status': 'approved'},
        })
        self.fb.set_data(f"User/Clientes/{CLIENT}", {
            'name': 'Carlos', 'phone': '3104445566', 'email': 'carlos@example.com'})

    def create(self, uid=CLIENT, **overrides):
        return self.api(uid).post(URL, body(**overrides), format='json')

    def created_request(self, response):
        return self.fb.get_data(f"requests/{response.json()['data']['request_id']}")

    def test_creates_request_with_frozen_reference(self):
        response = self.create(search_started_at=1791987120000, worker_selected_at=1791987300000)
        self.assertEqual(response.status_code, 201)
        data = response.json()['data']
        self.assertEqual(data['status'], 'pending')
        self.assertEqual((data['quote_reference']['min_cop'], data['quote_reference']['max_cop']), (68000, 153000))
        self.assertFalse(data['quote_reference']['has_unpriced_items'])

        request = self.created_request(response)
        self.assertEqual(request['request_id'], data['request_id'])
        self.assertEqual(request['id'], data['request_id'])
        self.assertEqual(request['client_id'], CLIENT)
        self.assertEqual((request['client_name'], request['client_phone'], request['client_email']),
                         ('Carlos', '3104445566', 'carlos@example.com'))
        self.assertEqual((request['worker_id'], request['worker_name'], request['worker_phone']),
                         (WORKER, 'Ana Gómez', '3001112233'))
        self.assertEqual((request['service_category'], request['service_type']), ('plomeria', 'Plomería'))
        self.assertEqual((request['lat'], request['lng']), (5.3086, -73.8150))
        self.assertEqual(request['task_items'], [
            {'task': 'destapar-desague-sanitario', 'quantity': 1},
            {'task': 'reparar-grifo-valvula', 'quantity': 1},
        ])
        self.assertEqual(request['quote_reference'], data['quote_reference'])
        self.assertEqual(request['status'], 'pending')
        self.assertFalse(request['is_rated'])
        self.assertEqual(request['search_started_at'], 1791987120000)
        self.assertEqual(request['worker_selected_at'], 1791987300000)
        self.assertNotIn('quoted_price', request)

    def test_notifies_the_worker(self):
        self.create()
        self.assertEqual(self.sent_notifications(), [('fcm-worker', 'new_request')])

    def test_reference_stays_frozen_when_rates_change(self):
        response = self.create()
        Task.objects.filter(slug='reparar-grifo-valvula').update(reference_min_cop=90000, reference_max_cop=200000)
        SystemConfig.objects.filter(key='quote_regional_factor_pct').update(value='0')
        self.assertEqual(self.created_request(response)['quote_reference']['min_cop'], 68000)

    def test_custom_item_and_decimal_quantity_are_stored(self):
        self.fb.update_data(f"User/Trabajadores/{WORKER}", {'categories': ['pintura']})
        response = self.create(service_category='pintura', task_items=[
            {'task': 'pintura-estuco-2-manos', 'quantity': 12.5},
            {'custom_description': 'Resanar grieta del techo', 'quantity': 1},
        ])
        self.assertEqual(response.status_code, 201)
        request = self.created_request(response)
        self.assertEqual(request['task_items'], [
            {'task': 'pintura-estuco-2-manos', 'quantity': 12.5},
            {'custom_description': 'Resanar grieta del techo', 'quantity': 1},
        ])
        self.assertTrue(request['quote_reference']['has_unpriced_items'])

    def test_legacy_work_field_is_accepted_until_migration(self):
        self.fb.set_data(f"User/Trabajadores/{WORKER}/categories", None)
        self.fb.set_data(f"User/Trabajadores/{WORKER}/work", 'Plomería')
        self.assertEqual(self.create().status_code, 201)

        self.fb.set_data(f"User/Trabajadores/{WORKER}/work", 'Electricista')
        self.assertEqual(self.create(service_category='electricidad', task_items=[
            {'task': 'breaker-falla-simple', 'quantity': 1}]).status_code, 201)

        self.fb.set_data(f"User/Trabajadores/{WORKER}/work", 'Plomero')
        self.assertEqual(self.create().status_code, 201)

        self.fb.set_data(f"User/Trabajadores/{WORKER}/work", 'Ferretería')
        self.assertEqual(self.create().status_code, 409)

    def test_worker_must_exist_be_verified_and_offer_the_category(self):
        self.assertEqual(self.create(worker_id='no-existe').status_code, 404)

        self.assertEqual(self.create(service_category='cerrajeria', task_items=[
            {'task': 'abrir-puerta', 'quantity': 1}]).status_code, 409)

        self.fb.set_data(f"User/Trabajadores/{WORKER}/isActive", False)
        self.assertEqual(self.create().status_code, 409)
        self.fb.set_data(f"User/Trabajadores/{WORKER}/isActive", True)

        for status in ('pending', 'documents_submitted', 'rejected'):
            self.fb.set_data(f"User/Trabajadores/{WORKER}/verificationStatus/status", status)
            response = self.create()
            self.assertEqual(response.status_code, 409)
            self.assertFalse(response.json()['success'])
        # No se escribió ninguna solicitud nueva
        self.assertEqual(list(self.fb.get_data('requests')), ['req-1'])

    def test_only_registered_clients_and_not_themselves(self):
        self.assertEqual(self.create(uid=OTHER).status_code, 403)
        self.fb.set_data(f"User/Clientes/{WORKER}", {'name': 'Ana'})
        self.assertEqual(self.create(uid=WORKER).status_code, 400)

    def test_invalid_bodies(self):
        cases = {
            'sin dirección': {'address': ''},
            'sin coordenada': {'lat': None},
            'latitud fuera de rango': {'lat': 91},
            'longitud fuera de rango': {'lng': -181},
            'id de trabajador inválido': {'worker_id': 'a/b'},
            'ítem de otro oficio': {'task_items': [{'task': 'abrir-puerta', 'quantity': 1}]},
            'sin ítems': {'task_items': []},
            'marca de tiempo no entera': {'search_started_at': 'ayer'},
        }
        for name, overrides in cases.items():
            with self.subTest(name):
                response = self.create(**overrides)
                self.assertEqual(response.status_code, 400)
                self.assertIn('errors', response.json())

    def test_requires_app_token(self):
        self.assertEqual(self.api().post(URL, body(), format='json').status_code, 401)
