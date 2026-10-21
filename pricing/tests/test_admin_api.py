from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from payments.tests.fakes import app_token, patch_verify_id_token
from worker_verification.models import SystemConfig

from ..models import ConfigAuditLog, ServiceCategory, Task


class AdminApiTestCase(TestCase):
    """Catálogo y parámetros desde el panel con auditoría (B10, I10)."""

    def setUp(self):
        cache.clear()  # contadores de throttling
        self.admin = User.objects.create_user('admin.ads', password='x', is_staff=True)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.admin)}")
        self.plomeria = ServiceCategory.objects.get(slug='plomeria')
        self.task = Task.objects.filter(category=self.plomeria).first()

    def test_catalog_includes_inactive_and_raw_reference(self):
        self.task.is_active = False
        self.task.save()
        response = self.client.get(reverse('pricing:admin-catalog'))
        self.assertEqual(response.status_code, 200)
        categories = {c['slug']: c for c in response.json()['data']}
        self.assertEqual(len(categories), 7)
        task = next(t for t in categories['plomeria']['tasks'] if t['id'] == self.task.id)
        self.assertFalse(task['is_active'])
        self.assertEqual(task['reference_min_cop'], self.task.reference_min_cop)

    def test_create_task_is_audited(self):
        response = self.client.post(reverse('pricing:admin-task-create'), {
            'category': 'plomeria', 'slug': 'cambiar-flotador', 'name': 'Cambiar flotador del tanque',
            'unit': 'unidad', 'reference_min_cop': 40000, 'reference_max_cop': 70000, 'source': 'Sondeo', 'order': 20,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        log = ConfigAuditLog.objects.get()
        self.assertEqual((log.admin, log.entity, log.entity_key, log.old_value),
                         (self.admin, 'Task', 'plomeria/cambiar-flotador', None))
        self.assertEqual(log.new_value['reference_max_cop'], 70000)

    def test_task_validation(self):
        url = reverse('pricing:admin-task-create')
        base = {'category': 'plomeria', 'slug': 'nueva', 'name': 'Nueva', 'unit': 'visita'}
        cases = [
            dict(base, unit='hora'),
            dict(base, reference_min_cop=50000),
            dict(base, reference_min_cop=90000, reference_max_cop=50000),
            dict(base, slug=self.task.slug),
            dict(base, category='plomeria-x'),
        ]
        for body in cases:
            with self.subTest(body=body):
                self.assertEqual(self.client.post(url, body, format='json').status_code, 400)
        self.assertFalse(ConfigAuditLog.objects.exists())

    def test_patch_task_deactivates_and_audits_old_and_new(self):
        url = reverse('pricing:admin-task', kwargs={'pk': self.task.pk})
        response = self.client.patch(url, {'is_active': False, 'reference_max_cop': self.task.reference_max_cop + 1000},
                                     format='json')
        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertFalse(self.task.is_active)
        log = ConfigAuditLog.objects.get()
        self.assertTrue(log.old_value['is_active'])
        self.assertFalse(log.new_value['is_active'])

        other = ServiceCategory.objects.get(slug='electricidad')
        self.assertEqual(self.client.patch(url, {'category': other.slug}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(reverse('pricing:admin-task', kwargs={'pk': 99999}), {},
                                           format='json').status_code, 404)

    def test_patch_without_changes_is_not_audited(self):
        url = reverse('pricing:admin-task', kwargs={'pk': self.task.pk})
        self.assertEqual(self.client.patch(url, {'name': self.task.name}, format='json').status_code, 200)
        self.assertFalse(ConfigAuditLog.objects.exists())

    def test_patch_category_keeps_slug(self):
        url = reverse('pricing:admin-category', kwargs={'pk': self.plomeria.pk})
        response = self.client.patch(url, {'is_active': False, 'slug': 'otra'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.plomeria.refresh_from_db()
        self.assertEqual((self.plomeria.slug, self.plomeria.is_active), ('plomeria', False))
        self.assertEqual(ConfigAuditLog.objects.get().entity, 'ServiceCategory')

    def test_config_list_and_patch(self):
        response = self.client.get(reverse('pricing:admin-config'))
        keys = [item['key'] for item in response.json()['data']]
        self.assertIn('quote_min_visit_fee_cop', keys)

        url = reverse('pricing:admin-config-detail', kwargs={'key': 'quote_min_visit_fee_cop'})
        response = self.client.patch(url, {'value': ' 27000 '}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['value'], '27000')
        log = ConfigAuditLog.objects.get()
        self.assertEqual((log.entity, log.entity_key, log.old_value['value'], log.new_value['value']),
                         ('SystemConfig', 'quote_min_visit_fee_cop', '25500', '27000'))

    def test_config_validation(self):
        cases = [
            ('quote_min_visit_fee_cop', 'mucho'),
            ('quote_min_visit_fee_cop', '27000.5'),
            ('quote_min_visit_fee_cop', '6000000'),   # no menor que el precio máximo
            ('quote_regional_factor_pct', '-95'),
            ('worker_max_categories', '0'),
            ('search_weight_rating', '1.5'),
        ]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                url = reverse('pricing:admin-config-detail', kwargs={'key': key})
                self.assertEqual(self.client.patch(url, {'value': value}, format='json').status_code, 400)
        url = reverse('pricing:admin-config-detail', kwargs={'key': 'no_existe'})
        self.assertEqual(self.client.patch(url, {'value': '1'}, format='json').status_code, 404)
        self.assertEqual(SystemConfig.objects.get(key='quote_min_visit_fee_cop').value, '25500')

    def test_audit_log_list(self):
        url = reverse('pricing:admin-config-detail', kwargs={'key': 'search_weight_rating'})
        self.client.patch(url, {'value': '0.4'}, format='json')
        response = self.client.get(reverse('pricing:admin-audit'), {'entity': 'SystemConfig'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['data'][0]['admin'], 'admin.ads')

    def test_app_token_is_refused(self):
        with patch_verify_id_token():
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {app_token('client-1')}")
            self.assertIn(client.get(reverse('pricing:admin-catalog')).status_code, (401, 403))
        self.assertEqual(APIClient().get(reverse('pricing:admin-config')).status_code, 401)
