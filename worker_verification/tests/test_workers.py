from unittest import mock

from accounts.services.account_service import account_service, email_key
from pricing.models import ConfigAuditLog, ServiceCategory

from ..models import SystemConfig
from ..services.bulk_worker_service import bulk_worker_service
from .base import ANA, BETO, CARO, CLIENT, PanelTestCase

WORKERS = '/api/workers/'


def new_worker(**overrides):
    body = {'name': 'Dora', 'lastName': 'León', 'email': 'Dora@ADS.test', 'categories': ['jardineria'],
            'phone': '310-555-1234'}
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

    def test_category_filter_uses_catalog_slugs(self):
        # DEF-10: el panel filtra con el slug; antes se comparaba con el texto viejo de `work`
        self.assertEqual(self.ids(self.client.get(WORKERS, {'category': 'plomeria'})), {ANA})
        # Sin `categories` (Beto, Caro) el oficio se deduce de `work`
        self.assertEqual(self.ids(self.client.get(WORKERS, {'category': 'electricidad'})), {BETO})
        self.assertEqual(self.ids(self.client.get(WORKERS, {'category': 'Pintor'})), {CARO})
        # Un trabajador con varios oficios aparece en cada uno
        self.fb.set_data(f'User/Trabajadores/{ANA}/categories', ['plomeria', 'electricidad'])
        self.assertEqual(self.ids(self.client.get(WORKERS, {'category': 'electricidad'})), {ANA, BETO})
        self.assertEqual(self.ids(self.client.get(WORKERS, {'category': 'ferreteria'})), set())

    def test_empty_database(self):
        self.fb.set_data('User/Trabajadores', None)
        self.assertEqual(self.client.get(WORKERS).json()['count'], 0)
        self.assertEqual(self.client.get(WORKERS, {'available': 'true'}).json()['count'], 0)
        self.assertEqual(self.client.get(f'{WORKERS}statistics/').json()['data']['total'], 0)

    def test_retrieve(self):
        response = self.client.get(f'{WORKERS}{ANA}/')
        self.assertEqual((response.status_code, response.json()['data']['name']), (200, 'Ana'))
        self.assertEqual(self.client.get(f'{WORKERS}no-existe/').status_code, 404)

    def test_list_includes_categories_and_verification_for_the_table(self):
        workers = {worker['id']: worker for worker in self.client.get(WORKERS).json()['data']}
        self.assertEqual(workers[ANA]['categories'], ['plomeria'])
        self.assertEqual(workers[ANA]['verificationStatus']['status'], 'approved')
        self.assertEqual(workers[BETO]['verificationStatus']['status'], 'documents_submitted')
        # Sin oficios ni verificación: lista vacía y null
        self.assertEqual((workers[CARO]['categories'], workers[CARO]['verificationStatus']), ([], None))

    def test_statistics(self):
        data = self.client.get(f'{WORKERS}statistics/').json()['data']
        self.assertEqual((data['total'], data['available'], data['online']), (3, 2, 1))
        self.assertEqual(data['by_category'], {'plomeria': 1, 'electricidad': 1, 'pintura': 1})
        self.fb.set_data(f'User/Trabajadores/{CARO}/work', 'Ferretería')
        by_category = self.client.get(f'{WORKERS}statistics/').json()['data']['by_category']
        self.assertEqual(by_category, {'plomeria': 1, 'electricidad': 1, 'sin_oficio': 1})

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
        # Como el registro de la app: oficios del catálogo y `work` con el primero
        self.assertEqual((stored['categories'], stored['work']), (['jardineria'], 'Jardinería'))

    def test_categories_follow_the_catalog_and_the_limit(self):
        # Acepta slug, nombre o el valor viejo de `work`, sin repetir; sin precio ni ubicación
        response = self.create(categories=['Plomero', 'pintura', 'Plomería'], pricePerHour=50000, latitude=5.3)
        self.assertEqual(response.status_code, 201)
        stored = self.worker('new-uid')
        self.assertEqual((stored['categories'], stored['work']), (['plomeria', 'pintura'], 'Plomería'))
        self.assertNotIn('pricePerHour', stored)
        self.assertNotIn('latitude', stored)

    def test_invalid_categories_are_refused(self):
        ServiceCategory.objects.filter(slug='cerrajeria').update(is_active=False)
        cases = {
            'vacío': [], 'no es oficio': ['ferreteria'], 'inactivo': ['cerrajeria'],
            'más de 3': ['plomeria', 'pintura', 'electricidad', 'jardineria'],
        }
        for label, categories in cases.items():
            with self.subTest(label):
                response = self.create(categories=categories)
                self.assertEqual(response.status_code, 400)
                self.assertIn('categories', response.json()['errors'])
        self.assertIsNone(self.worker('new-uid'))
        # El máximo sale de SystemConfig (worker_max_categories)
        SystemConfig.objects.filter(key='worker_max_categories').update(value='4')
        self.assertEqual(self.create(categories=cases['más de 3']).status_code, 201)

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
        for overrides in ({'email': 'no-es-correo'}, {'phone': '12'}, {'categories': None}, {'name': ''}):
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

    def test_put_updates_categories_but_not_price_or_location(self):
        response = self.client.put(f'{WORKERS}{CARO}/', {'categories': ['pintura', 'carpinteria'],
                                                         'pricePerHour': 9, 'latitude': 1}, format='json')
        self.assertEqual(response.status_code, 200)
        caro = self.worker(CARO)
        self.assertEqual((caro['categories'], caro['work']), (['pintura', 'carpinteria'], 'Pintura'))
        self.assertNotIn('pricePerHour', caro)
        self.assertNotEqual(caro.get('latitude'), 1)
        response = self.client.patch(f'{WORKERS}{CARO}/', {'categories': ['ferreteria']}, format='json')
        self.assertEqual(response.status_code, 400)

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
        """Elimina la cuenta completa, también la de Firebase Auth, y queda en la auditoría (DEF-34)."""
        self.fb.set_data(f'Tokens/{CARO}', {'token': 'fcm-caro'})
        self.fb.set_data('requests/r1', {'worker_id': CARO, 'client_id': CLIENT, 'worker_name': 'Caro Díaz',
                                         'worker_phone': '300', 'status': 'pending'})
        with mock.patch.object(account_service, 'firebase', self.fb), \
                mock.patch.object(account_service, 'notifications') as notifications, \
                mock.patch('accounts.services.account_service.firebase_auth.get_user', side_effect=Exception('x')),                 mock.patch('accounts.services.account_service.firebase_auth.delete_user') as delete_user:
            self.assertEqual(self.client.delete(f'{WORKERS}{CARO}/').status_code, 200)

        delete_user.assert_called_once_with(CARO)
        self.assertIsNone(self.worker(CARO))
        self.assertIsNone(self.fb.get_data(f'Tokens/{CARO}'))
        request = self.fb.get_data('requests/r1')
        self.assertEqual((request['status'], request['worker_name']), ('cancelled', 'Usuario eliminado'))
        notifications.notify.assert_called_once()
        # El login de Caro dirá que el equipo de ADS eliminó su cuenta
        self.assertEqual(self.fb.get_data(f"deleted_accounts/{email_key('caro@ads.test')}")['deleted_by'], 'admin')
        log = ConfigAuditLog.objects.get(entity='Account', entity_key=CARO)
        self.assertEqual((log.admin, log.new_value['deleted']), (self.admin, True))

    def test_delete_with_service_in_progress_is_409(self):
        self.fb.set_data('requests/r1', {'worker_id': CARO, 'client_id': CLIENT, 'status': 'in_progress'})
        with mock.patch.object(account_service, 'firebase', self.fb), \
                mock.patch('accounts.services.account_service.firebase_auth.delete_user') as delete_user:
            response = self.client.delete(f'{WORKERS}{CARO}/')

        self.assertEqual(response.status_code, 409)
        self.assertIn('en camino o en progreso', response.json()['error'])
        delete_user.assert_not_called()
        self.assertIsNotNone(self.worker(CARO))
        self.assertFalse(ConfigAuditLog.objects.exists())
        self.assertEqual(self.client.delete(f'{WORKERS}no-existe/').status_code, 404)

    def test_verification_status_validation(self):
        url = f'{WORKERS}{BETO}/verification_status/'
        self.assertEqual(self.client.patch(url, {'status': 'aprobadisimo'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(f'{WORKERS}fantasma/verification_status/', {'status': 'approved'},
                                           format='json').status_code, 404)
        response = self.client.patch(url, {'status': 'approved'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.worker(BETO)['verificationStatus']['status'], 'approved')
