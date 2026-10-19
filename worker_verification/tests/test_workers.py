from unittest import mock

from ..services.bulk_worker_service import bulk_worker_service
from .base import ANA, BETO, CARO, CLIENT, PanelTestCase

WORKERS = '/api/workers/'


def new_worker(**overrides):
    body = {'name': 'Dora', 'lastName': 'León', 'email': 'Dora@ADS.test', 'work': 'Jardinería',
            'phone': '310-555-1234', 'latitude': 5.3086, 'longitude': -73.815}
    body.update(overrides)
    return body


class WorkerQueryTests(PanelTestCase):

    def ids(self, response):
        self.assertEqual(response.status_code, 200)
        return {worker['id'] for worker in response.json()['data']}

    def test_list_and_filters(self):
        self.assertEqual(self.ids(self.client.get(WORKERS)), {ANA, BETO, CARO})
        self.assertEqual(self.ids(self.client.get(WORKERS, {'available': 'true'})), {ANA, BETO})
        self.assertEqual(self.ids(self.client.get(WORKERS, {'online': 'true'})), {ANA})
        self.assertEqual(self.ids(self.client.get(WORKERS, {'search': 'rojas'})), {ANA})
        self.assertEqual(self.ids(self.client.get(WORKERS, {'search': 'beto@'})), {BETO})
        self.assertEqual(self.ids(self.client.get(WORKERS, {'search': 'pint'})), {CARO})
        # El filtro por oficio todavía compara el texto viejo de `work` (DEF-10 en contexto/pruebas/DEFECTOS.md)
        self.assertEqual(self.ids(self.client.get(WORKERS, {'category': 'Electricista'})), {BETO})

    def test_empty_database(self):
        self.fb.set_data('User/Trabajadores', None)
        self.assertEqual(self.client.get(WORKERS).json()['count'], 0)
        self.assertEqual(self.client.get(WORKERS, {'available': 'true'}).json()['count'], 0)
        self.assertEqual(self.client.get(f'{WORKERS}statistics/').json()['data']['total'], 0)

    def test_retrieve(self):
        response = self.client.get(f'{WORKERS}{ANA}/')
        self.assertEqual((response.status_code, response.json()['data']['name']), (200, 'Ana'))
        self.assertEqual(self.client.get(f'{WORKERS}no-existe/').status_code, 404)

    def test_statistics(self):
        data = self.client.get(f'{WORKERS}statistics/').json()['data']
        self.assertEqual((data['total'], data['available'], data['online']), (3, 2, 1))
        self.assertEqual(data['by_category'], {'Plomería': 1, 'Electricista': 1, 'Pintor': 1})

    def test_firebase_error_is_500(self):
        with mock.patch.object(self.fb, 'get_data', side_effect=Exception('caído')):
            self.assertEqual(self.client.get(WORKERS).status_code, 500)
            self.assertEqual(self.client.get(f'{WORKERS}{ANA}/').status_code, 500)
            self.assertEqual(self.client.get(f'{WORKERS}statistics/').status_code, 500)


class WorkerCreateTests(PanelTestCase):

    def create(self, auth_result=('new-uid', 'Gener4da!x', None), **overrides):
        with mock.patch.object(bulk_worker_service, 'create_firebase_auth_user', return_value=auth_result) as auth:
            response = self.client.post(WORKERS, new_worker(**overrides), format='json')
        self.auth_call = auth.call_args
        return response

    def test_creates_auth_user_and_profile(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['password'], 'Gener4da!x')
        stored = self.worker('new-uid')
        self.assertEqual((stored['email'], stored['phone'], stored['isAvailable'], stored['rating']),
                         ('dora@ads.test', '3105551234', True, 0.0))
        self.assertNotIn('password', stored)
        self.assertEqual(self.auth_call.args, ('dora@ads.test', '', 'Dora León'))

    def test_existing_auth_user_without_profile_gets_one(self):
        response = self.create(auth_result=('old-uid', None, 'Usuario ya existe en Firebase Auth'))
        self.assertEqual(response.status_code, 201)
        self.assertIn('warning', response.json())
        self.assertIsNotNone(self.worker('old-uid'))

    def test_email_of_an_existing_ads_account_is_refused(self):
        # Antes sobrescribía todo el perfil (verificación y rating) o le daba al cliente el rol de trabajador
        for uid in (ANA, CLIENT):
            with self.subTest(uid=uid):
                response = self.create(auth_result=(uid, None, 'Usuario ya existe en Firebase Auth'))
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.worker(ANA)['verificationStatus']['status'], 'approved')
        self.assertEqual(self.worker(ANA)['rating'], 4.5)
        self.assertIsNone(self.worker(CLIENT))

    def test_validation_and_auth_errors(self):
        for overrides in ({'email': 'no-es-correo'}, {'phone': '12'}, {'latitude': 91}, {'name': ''}):
            with self.subTest(overrides=overrides):
                self.assertEqual(self.create(**overrides).status_code, 400)
        self.assertEqual(self.create(auth_result=(None, None, 'cuota excedida')).status_code, 400)
        self.assertIsNone(self.worker('new-uid'))


class WorkerUpdateTests(PanelTestCase):

    def test_put_only_writes_sent_fields_and_never_the_rating(self):
        response = self.client.put(f'{WORKERS}{ANA}/', {'name': 'Ana María', 'rating': 1, 'totalRatings': 99},
                                   format='json')
        self.assertEqual(response.status_code, 200)
        ana = self.worker(ANA)
        self.assertEqual(ana['name'], 'Ana María')
        # Antes el PUT dejaba rating y totalRatings en 0 y volvía a poner isAvailable en true
        self.assertEqual((ana['rating'], ana['totalRatings'], ana['isOnline']), (4.5, 2, True))
        self.assertEqual(self.worker(CARO)['isAvailable'], False)

    def test_patch(self):
        self.assertEqual(self.client.patch(f'{WORKERS}{BETO}/', {'phone': '3200000000'}, format='json').status_code, 200)
        self.assertEqual(self.worker(BETO)['phone'], '3200000000')
        self.assertEqual(self.client.patch(f'{WORKERS}{BETO}/', {'email': 'malo'}, format='json').status_code, 400)

    def test_unknown_worker_is_404_without_creating_it(self):
        # update_data de Firebase crea el nodo: antes quedaban trabajadores «fantasma»
        cases = [
            ('put', '', {'name': 'X'}), ('patch', '', {'name': 'X'}), ('delete', '', None),
            ('patch', 'availability/', {'isAvailable': True}), ('patch', 'online_status/', {'isOnline': True}),
            ('patch', 'location/', {'latitude': 5.3, 'longitude': -73.8}), ('post', 'add_rating/', {'rating': 5}),
        ]
        for method, action, body in cases:
            with self.subTest(action=action or method):
                response = getattr(self.client, method)(f'{WORKERS}fantasma/{action}', body, format='json')
                self.assertEqual(response.status_code, 404)
        self.assertIsNone(self.worker('fantasma'))

    def test_availability_online_and_location(self):
        self.client.patch(f'{WORKERS}{CARO}/availability/', {'isAvailable': True}, format='json')
        self.client.patch(f'{WORKERS}{CARO}/online_status/', {'isOnline': True}, format='json')
        self.client.patch(f'{WORKERS}{CARO}/location/', {'latitude': 5.3086, 'longitude': -73.815}, format='json')
        caro = self.worker(CARO)
        self.assertEqual((caro['isAvailable'], caro['isOnline'], caro['latitude']), (True, True, 5.3086))

        self.assertEqual(self.client.patch(f'{WORKERS}{CARO}/availability/', {}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(f'{WORKERS}{CARO}/location/', {'latitude': 'x'}, format='json').status_code, 400)

    def test_add_rating_recalculates_average(self):
        self.client.post(f'{WORKERS}{ANA}/add_rating/', {'rating': 3}, format='json')
        self.assertEqual((self.worker(ANA)['rating'], self.worker(ANA)['totalRatings']), (4.0, 3))
        self.client.post(f'{WORKERS}{CARO}/add_rating/', {'rating': 5}, format='json')
        self.assertEqual((self.worker(CARO)['rating'], self.worker(CARO)['totalRatings']), (5, 1))
        self.assertEqual(self.client.post(f'{WORKERS}{ANA}/add_rating/', {'rating': 6}, format='json').status_code, 400)

    def test_delete(self):
        self.assertEqual(self.client.delete(f'{WORKERS}{CARO}/').status_code, 200)
        self.assertIsNone(self.worker(CARO))

    def test_verification_status_validation(self):
        url = f'{WORKERS}{BETO}/verification_status/'
        self.assertEqual(self.client.patch(url, {'status': 'aprobadisimo'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(f'{WORKERS}fantasma/verification_status/', {'status': 'approved'},
                                           format='json').status_code, 404)
        response = self.client.patch(url, {'status': 'approved'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.worker(BETO)['verificationStatus']['status'], 'approved')
