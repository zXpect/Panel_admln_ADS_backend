from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from payments.tests.fakes import app_token, patch_verify_id_token
from worker_verification.models import SystemConfig

from ..admin import SystemConfigAdmin, TaskAdmin
from ..models import ConfigAuditLog, ServiceCategory, Task
from ..services import pricing_service, round_to_hundred

# Rango de Ubaté de la Tabla 5 del Anexo 4 (−15 %, a la centena)
TABLE_5 = {
    'destapar-desague-sanitario': (25500, 51000),
    'reparar-grifo-valvula': (42500, 102000),
    'instalar-calentador': (170000, 297500),
    'breaker-falla-simple': (34000, 68000),
    'instalar-lampara-ventilador': (51000, 102000),
    'instalar-tomacorriente': (68000, 127500),
    'diagnosticar-reparar-circuito': (85000, 212500),
    'pintura-estuco-2-manos': (6000, 7700),
    'estuco-pintura-3-manos': (14900, 18700),
    'pintar-puerta-esmalte': (19600, 29800),
    'instalar-ceramica-piso': (20400, 25100),
    'enchape-muros-bano': (24200, 29800),
    'panete-liso-muros': (15700, 18700),
    'muro-bloque-concreto': (23800, 28100),
    'alistado-piso': (11900, 14900),
    'maestro-obra-jornada': (85000, 153000),
}

CLIENT = 'client-1'


class RoundingTests(TestCase):

    def test_halves_round_up_not_to_even(self):
        self.assertEqual(round_to_hundred(Decimal('7650')), 7700)
        self.assertEqual(round_to_hundred(Decimal('14875')), 14900)
        self.assertEqual(round_to_hundred(Decimal('7649.99')), 7600)
        self.assertEqual(round_to_hundred(Decimal('25075')), 25100)


class SeedTests(TestCase):

    def test_seed_has_seven_categories_and_34_tasks(self):
        self.assertEqual(
            list(ServiceCategory.objects.values_list('slug', flat=True)),
            ['electricidad', 'plomeria', 'pintura', 'albanileria', 'cerrajeria', 'jardineria', 'carpinteria'])
        self.assertEqual(Task.objects.count(), 34)
        self.assertEqual(Task.objects.filter(reference_min_cop__isnull=False).count(), 16)
        # Cerrajería, jardinería y carpintería no tienen rango (Anexo 4, D3)
        self.assertFalse(Task.objects.filter(
            category__slug__in=['cerrajeria', 'jardineria', 'carpinteria'],
            reference_min_cop__isnull=False).exists())

    def test_seed_creates_config_keys(self):
        config = dict(SystemConfig.objects.values_list('key', 'value'))
        self.assertEqual(config['quote_regional_factor_pct'], '-15')
        self.assertEqual(config['quote_min_visit_fee_cop'], '25500')
        self.assertEqual(config['quote_max_price_cop'], '5000000')
        self.assertEqual(config['worker_max_categories'], '3')

    def test_table_5_ranges(self):
        factor = pricing_service.regional_factor_pct()
        for task in Task.objects.filter(reference_min_cop__isnull=False):
            with self.subTest(task=task.slug):
                self.assertEqual(pricing_service.task_range(task, factor), TABLE_5[task.slug])
        self.assertEqual(
            set(Task.objects.filter(reference_min_cop__isnull=False).values_list('slug', flat=True)),
            set(TABLE_5))


class PricingApiTestCase(TestCase):

    def setUp(self):
        cache.clear()  # contadores de throttling
        verify = patch_verify_id_token()
        verify.start()
        self.addCleanup(verify.stop)

    def api(self, uid=CLIENT):
        client = APIClient()
        if uid:
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {app_token(uid)}")
        return client

    def estimate(self, task_items, category='plomeria'):
        return self.api().post(
            reverse('pricing:estimate'), {'service_category': category, 'task_items': task_items}, format='json')


class CatalogApiTests(PricingApiTestCase):

    def catalog(self):
        response = self.api().get(reverse('pricing:catalog'))
        self.assertEqual(response.status_code, 200)
        return response.json()['data']

    def tasks(self, data):
        return {task['slug']: task for category in data['categories'] for task in category['tasks']}

    def test_catalog_shape_and_ubate_ranges(self):
        data = self.catalog()
        self.assertEqual(data['regional_factor_pct'], -15)
        self.assertEqual(data['min_visit_fee_cop'], 25500)
        self.assertEqual(data['categories'][1]['slug'], 'plomeria')
        self.assertEqual(data['categories'][1]['name'], 'Plomería')

        tasks = self.tasks(data)
        self.assertEqual(len(tasks), 34)
        self.assertEqual(tasks['destapar-desague-sanitario'], {
            'slug': 'destapar-desague-sanitario', 'name': 'Destapar desagüe o sanitario',
            'unit': 'visita', 'min_cop': 25500, 'max_cop': 51000})
        self.assertIsNone(tasks['reparar-fuga-tuberia']['min_cop'])
        self.assertIsNone(tasks['reparar-fuga-tuberia']['max_cop'])
        for slug, expected in TABLE_5.items():
            self.assertEqual((tasks[slug]['min_cop'], tasks[slug]['max_cop']), expected)

    def test_inactive_tasks_and_categories_are_hidden(self):
        Task.objects.filter(slug='abrir-puerta').update(is_active=False)
        ServiceCategory.objects.filter(slug='carpinteria').update(is_active=False)
        data = self.catalog()
        self.assertNotIn('abrir-puerta', self.tasks(data))
        self.assertNotIn('carpinteria', [category['slug'] for category in data['categories']])

    def test_regional_factor_change_takes_effect(self):
        SystemConfig.objects.filter(key='quote_regional_factor_pct').update(value='-20')
        tasks = self.tasks(self.catalog())
        # 30.000 × 0,80 y 60.000 × 0,80
        self.assertEqual((tasks['destapar-desague-sanitario']['min_cop'],
                          tasks['destapar-desague-sanitario']['max_cop']), (24000, 48000))

    def test_requires_app_token(self):
        self.assertEqual(self.api(uid=None).get(reverse('pricing:catalog')).status_code, 401)
        self.assertEqual(self.api(uid='revoked').get(reverse('pricing:catalog')).status_code, 401)

    def test_panel_jwt_is_not_accepted(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(User.objects.create_user('admin'))}")
        self.assertEqual(client.get(reverse('pricing:catalog')).status_code, 401)


class EstimateApiTests(PricingApiTestCase):

    def test_example_from_api_spec(self):
        response = self.estimate([
            {'task': 'destapar-desague-sanitario', 'quantity': 1},
            {'task': 'reparar-grifo-valvula', 'quantity': 1},
            {'custom_description': 'Revisar humedad detrás del lavamanos', 'quantity': 1},
        ])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'success': True,
            'data': {
                'min_cop': 68000,
                'max_cop': 153000,
                'regional_factor_pct': -15,
                'min_visit_fee_cop': 25500,
                'has_unpriced_items': True,
                'items': [
                    {'task': 'destapar-desague-sanitario', 'quantity': 1, 'unit': 'visita',
                     'min_cop': 25500, 'max_cop': 51000},
                    {'task': 'reparar-grifo-valvula', 'quantity': 1, 'unit': 'unidad',
                     'min_cop': 42500, 'max_cop': 102000},
                    {'custom_description': 'Revisar humedad detrás del lavamanos', 'quantity': 1,
                     'unit': None, 'min_cop': None, 'max_cop': None},
                ],
            },
        })

    def test_decimal_quantity_in_m2(self):
        response = self.estimate([{'task': 'pintura-estuco-2-manos', 'quantity': 12.5}], category='pintura')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        # 6.000 × 12,5 = 75.000 y 7.700 × 12,5 = 96.250 -> 96.300
        self.assertEqual((data['min_cop'], data['max_cop']), (75000, 96300))
        self.assertEqual(data['items'][0]['quantity'], 12.5)
        self.assertFalse(data['has_unpriced_items'])

    def test_quantity_multiplies_the_rounded_unit_price(self):
        # El cliente ve 7.700 por m² en el catálogo: 2 m² son 15.400 (no 9.000 × 0,85 × 2 = 15.300)
        data = self.estimate([{'task': 'pintura-estuco-2-manos', 'quantity': 2},
                              {'task': 'pintar-puerta-esmalte', 'quantity': 1}], category='pintura').json()['data']
        self.assertEqual(data['items'][0]['max_cop'], 15400)
        self.assertEqual(data['max_cop'], 15400 + 29800)

    def test_min_visit_fee_is_the_floor(self):
        data = self.estimate([{'task': 'pintura-estuco-2-manos', 'quantity': 2.3}], category='pintura').json()['data']
        # 13.800 – 17.700 quedan por debajo de la tarifa mínima
        self.assertEqual(data['items'][0]['min_cop'], 13800)
        self.assertEqual(data['items'][0]['max_cop'], 17700)
        self.assertEqual((data['min_cop'], data['max_cop']), (25500, 25500))

        data = self.estimate([{'task': 'pintar-puerta-esmalte', 'quantity': 1}], category='pintura').json()['data']
        self.assertEqual((data['min_cop'], data['max_cop']), (25500, 29800))

    def test_only_unpriced_items(self):
        response = self.estimate([{'task': 'abrir-puerta', 'quantity': 1},
                                  {'custom_description': 'Cambiar cilindro', 'quantity': 2}], category='cerrajeria')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertIsNone(data['min_cop'])
        self.assertIsNone(data['max_cop'])
        self.assertTrue(data['has_unpriced_items'])
        self.assertEqual(data['items'][0], {'task': 'abrir-puerta', 'quantity': 1, 'unit': 'visita',
                                            'min_cop': None, 'max_cop': None})

    def test_deactivated_task_or_category_is_rejected(self):
        Task.objects.filter(slug='destapar-desague-sanitario').update(is_active=False)
        response = self.estimate([{'task': 'destapar-desague-sanitario', 'quantity': 1}])
        self.assertEqual(response.status_code, 400)
        self.assertIn('task', response.json()['errors']['task_items']['0'])

        ServiceCategory.objects.filter(slug='plomeria').update(is_active=False)
        response = self.estimate([{'task': 'reparar-grifo-valvula', 'quantity': 1}])
        self.assertEqual(response.status_code, 400)
        self.assertIn('service_category', response.json()['errors'])

    def test_invalid_items_are_rejected(self):
        cases = {
            'tarea de otro oficio': ([{'task': 'abrir-puerta', 'quantity': 1}], 'plomeria'),
            'tarea inexistente': ([{'task': 'no-existe', 'quantity': 1}], 'plomeria'),
            'oficio inexistente': ([{'task': 'abrir-puerta', 'quantity': 1}], 'ferreteria'),
            'cantidad cero': ([{'task': 'reparar-grifo-valvula', 'quantity': 0}], 'plomeria'),
            'cantidad negativa': ([{'task': 'reparar-grifo-valvula', 'quantity': -1}], 'plomeria'),
            'decimal fuera de m2': ([{'task': 'reparar-grifo-valvula', 'quantity': 1.5}], 'plomeria'),
            'decimal en «Otro»': ([{'custom_description': 'Algo', 'quantity': 1.5}], 'plomeria'),
            'sin tarea ni descripción': ([{'quantity': 1}], 'plomeria'),
            'tarea y descripción': ([{'task': 'reparar-grifo-valvula', 'custom_description': 'x',
                                      'quantity': 1}], 'plomeria'),
            'sin cantidad': ([{'task': 'reparar-grifo-valvula'}], 'plomeria'),
            'sin ítems': ([], 'plomeria'),
            'más de 10 ítems': ([{'task': 'reparar-grifo-valvula', 'quantity': 1}] * 11, 'plomeria'),
        }
        for name, (items, category) in cases.items():
            with self.subTest(name):
                response = self.estimate(items, category=category)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()['success'])
                self.assertIn('errors', response.json())

    def test_ten_items_are_allowed(self):
        response = self.estimate([{'task': 'reparar-grifo-valvula', 'quantity': 1}] * 10)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['min_cop'], 425000)

    def test_requires_app_token(self):
        response = self.api(uid=None).post(reverse('pricing:estimate'), {}, format='json')
        self.assertEqual(response.status_code, 401)


class ConfigAuditTests(TestCase):
    """Los cambios hechos desde el admin de Django quedan en ConfigAuditLog (I10)."""

    def setUp(self):
        self.admin_user = User.objects.create_superuser('admin', password='x')
        self.request = RequestFactory().post('/')
        self.request.user = self.admin_user

    def test_task_change_is_audited(self):
        task = Task.objects.get(slug='abrir-puerta')
        task.reference_min_cop, task.reference_max_cop = 30000, 50000
        TaskAdmin(Task, AdminSite()).save_model(self.request, task, form=None, change=True)

        log = ConfigAuditLog.objects.get()
        self.assertEqual((log.admin, log.entity, log.entity_key), (self.admin_user, 'Task', 'cerrajeria/abrir-puerta'))
        self.assertIsNone(log.old_value['reference_min_cop'])
        self.assertEqual(log.new_value['reference_min_cop'], 30000)

    def test_config_change_is_audited_and_unchanged_save_is_not(self):
        config = SystemConfig.objects.get(key='quote_min_visit_fee_cop')
        model_admin = SystemConfigAdmin(SystemConfig, AdminSite())
        model_admin.save_model(self.request, config, form=None, change=True)
        self.assertFalse(ConfigAuditLog.objects.exists())

        config.value = '27000'
        model_admin.save_model(self.request, config, form=None, change=True)
        log = ConfigAuditLog.objects.get()
        self.assertEqual((log.entity, log.entity_key), ('SystemConfig', 'quote_min_visit_fee_cop'))
        self.assertEqual((log.old_value['value'], log.new_value['value']), ('25500', '27000'))

    def test_catalog_cannot_be_deleted_from_admin(self):
        self.assertFalse(TaskAdmin(Task, AdminSite()).has_delete_permission(self.request))
