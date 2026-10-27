from io import StringIO
import re

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from accounts.evaluators import EVALUATOR_GROUP


class EvaluatorRoleTests(TestCase):
    """Rol de evaluador (jurados): lectura y revisión sí; borrar, carga masiva y tarifas no."""

    def setUp(self):
        cache.clear()  # contadores de throttling
        self.evaluator = User.objects.create_user('jurado1', password='clave-jurado')
        self.evaluator.groups.add(Group.objects.get_or_create(name=EVALUATOR_GROUP)[0])
        self.admin = User.objects.create_user('admin.ads', password='clave-admin')

    def client_for(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
        return client

    def assertForbidden(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'evaluator_forbidden')

    def test_blocks_destructive_and_configuration_actions(self):
        api = self.client_for(self.evaluator)
        self.assertForbidden(api.delete('/api/workers/worker-1/'))
        self.assertForbidden(api.post('/api/workers/', {}, format='json'))
        self.assertForbidden(api.patch('/api/workers/worker-1/', {}, format='json'))
        self.assertForbidden(api.delete('/api/documents/delete/', {}, format='json'))
        self.assertForbidden(api.post('/api/workers/bulk-upload/', {}, format='multipart'))
        self.assertForbidden(api.patch('/api/admin/catalog/tasks/1/', {'base_price': 1}, format='json'))
        self.assertForbidden(api.patch('/api/admin/config/minimum_visit_fee/', {'value': '1'}, format='json'))

    def test_allows_reading(self):
        response = self.client_for(self.evaluator).get('/api/admin/config/')
        self.assertEqual(response.status_code, 200)

    def test_review_actions_reach_their_view(self):
        api = self.client_for(self.evaluator)
        # Las respuestas vienen de la vista (no existe / dato inválido), no del bloqueo del rol
        self.assertEqual(api.patch('/api/pqr/999/', {'status': 'closed'}, format='json').status_code, 400)
        self.assertEqual(api.patch('/api/admin/accounts/uid.invalido/status/', {'is_active': False},
                                   format='json').status_code, 400)

    def test_admin_is_not_restricted(self):
        response = self.client_for(self.admin).patch('/api/admin/config/minimum_visit_fee/', {}, format='json')
        self.assertNotEqual(response.status_code, 403)

    def test_login_token_carries_role(self):
        api = APIClient()
        evaluator = api.post('/api/auth/token/', {'username': 'jurado1', 'password': 'clave-jurado'})
        admin = api.post('/api/auth/token/', {'username': 'admin.ads', 'password': 'clave-admin'})
        self.assertEqual(AccessToken(evaluator.data['access'])['role'], 'evaluador')
        self.assertEqual(AccessToken(evaluator.data['access'])['access_until'], '2026-11-28')
        self.assertEqual(AccessToken(admin.data['access'])['role'], 'admin')

    @override_settings(EVALUATOR_ACCESS_UNTIL='2020-01-01')
    def test_expired_access_blocks_login_and_reads(self):
        login = APIClient().post('/api/auth/token/', {'username': 'jurado1', 'password': 'clave-jurado'})
        self.assertEqual(login.status_code, 401)
        response = self.client_for(self.evaluator).get('/api/admin/config/')
        self.assertEqual(response.status_code, 403)
        self.assertIn('terminó', response.json()['error'])
        # Los administradores siguen entrando
        self.assertEqual(self.client_for(self.admin).get('/api/admin/config/').status_code, 200)


class EvaluatorCommandTests(TestCase):
    """manage.py evaluadores: crear, restablecer, listar y desactivar."""

    def run_command(self, *args):
        out = StringIO()
        call_command('evaluadores', *args, stdout=out)
        return out.getvalue()

    def test_create_prints_working_passwords_once(self):
        output = self.run_command('crear', 'jurado1', 'jurado2', '--nombre', 'Jurado 1')
        passwords = dict(re.findall(r'usuario: (\S+)\s+contraseña: (\S+)', output))

        self.assertEqual(set(passwords), {'jurado1', 'jurado2'})
        for username, password in passwords.items():
            user = User.objects.get(username=username)
            self.assertTrue(user.check_password(password))
            self.assertFalse(user.is_staff or user.is_superuser)
            self.assertTrue(user.groups.filter(name=EVALUATOR_GROUP).exists())
        self.assertEqual(User.objects.get(username='jurado1').first_name, 'Jurado 1')

    def test_create_refuses_existing_users(self):
        User.objects.create_user('jurado1')
        with self.assertRaises(CommandError):
            self.run_command('crear', 'jurado1')

    def test_reset_and_deactivate(self):
        self.run_command('crear', 'jurado1')
        self.run_command('desactivar')
        self.assertFalse(User.objects.get(username='jurado1').is_active)

        output = self.run_command('restablecer', 'jurado1')
        password = re.search(r'contraseña: (\S+)', output).group(1)
        user = User.objects.get(username='jurado1')
        self.assertTrue(user.is_active and user.check_password(password))

    def test_reset_only_touches_evaluators(self):
        User.objects.create_user('admin.ads')
        with self.assertRaises(CommandError):
            self.run_command('restablecer', 'admin.ads')
