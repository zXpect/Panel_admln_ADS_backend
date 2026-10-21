from unittest import mock

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.services.account_service import account_service
from payments.tests.test_api import CLIENT, WORKER, AppApiTestCase
from pricing.models import ConfigAuditLog


class AccountStatusTests(AppApiTestCase):
    """PATCH /api/admin/accounts/{uid}/status/ (RF-21, HU-32): suspender y reactivar cuentas."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(account_service, 'firebase', self.fb)
        patcher.start()
        self.addCleanup(patcher.stop)
        auth = mock.patch('accounts.services.account_service.firebase_auth')
        self.auth = auth.start()
        self.addCleanup(auth.stop)
        # La excepción real, para que el except del servicio la reconozca
        from firebase_admin import auth as real_auth
        self.auth.UserNotFoundError = real_auth.UserNotFoundError

        self.admin = User.objects.create_user('revisora', password='x')
        self.panel = APIClient()
        self.panel.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(self.admin).access_token}')

        self.fb.set_data(f"User/Clientes/{CLIENT}", {'name': 'Carla', 'lastName': 'Ruiz', 'email': 'c@x.co'})
        self.fb.update_data(f"User/Trabajadores/{WORKER}", {'isAvailable': True, 'isOnline': True})
        self.fb.set_data(f"active_workers/{WORKER}", {'g': 'x', 'l': [5.3, -73.8]})
        self.fb.set_data('requests/req-2', {'client_id': 'otro-cliente', 'worker_id': WORKER,
                                            'client_name': 'Pedro', 'status': 'accepted'})

    def change(self, uid, is_active, client=None, **extra):
        return (client or self.panel).patch(reverse('accounts:admin-account-status', kwargs={'uid': uid}),
                                            {'is_active': is_active, **extra}, format='json')

    def test_suspend_worker(self):
        self.set_request(status='completed')

        response = self.change(WORKER, False, reason='Incumplió los términos')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data'], {'uid': WORKER, 'role': 'worker', 'is_active': False})
        self.auth.update_user.assert_called_once_with(WORKER, disabled=True)
        self.auth.revoke_refresh_tokens.assert_called_once_with(WORKER)
        worker = self.fb.get_data(f"User/Trabajadores/{WORKER}")
        self.assertEqual((worker['isActive'], worker['isAvailable'], worker['isOnline']), (False, False, False))
        self.assertIsNone(self.fb.get_data(f"active_workers/{WORKER}"))

        # Lo que no había iniciado se cancela con aviso; lo terminado no se toca
        cancelled = self.fb.get_data('requests/req-2')
        self.assertEqual((cancelled['status'], cancelled['cancelled_by'], cancelled['cancellation_reason_text']),
                         ('cancelled', 'worker', 'Cuenta suspendida'))
        self.assertEqual(self.request_data()['status'], 'completed')

        log = ConfigAuditLog.objects.get()
        self.assertEqual((log.admin, log.entity, log.entity_key), (self.admin, 'Account', WORKER))
        self.assertEqual(log.old_value, {'is_active': True})
        self.assertEqual(log.new_value, {'is_active': False, 'role': 'worker', 'reason': 'Incumplió los términos'})

    def test_reactivate_client(self):
        self.fb.update_data(f"User/Clientes/{CLIENT}", {'isActive': False})

        response = self.change(CLIENT, True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data']['role'], 'client')
        self.auth.update_user.assert_called_once_with(CLIENT, disabled=False)
        self.auth.revoke_refresh_tokens.assert_not_called()
        self.assertTrue(self.fb.get_data(f"User/Clientes/{CLIENT}/isActive"))
        log = ConfigAuditLog.objects.get()
        self.assertEqual((log.old_value, log.new_value['is_active']), ({'is_active': False}, True))

    def test_service_in_progress_blocks_suspension(self):
        self.set_request(status='on_the_way')

        response = self.change(CLIENT, False)

        self.assertEqual(response.status_code, 409)
        self.auth.update_user.assert_not_called()
        self.assertIsNone(self.fb.get_data(f"User/Clientes/{CLIENT}/isActive"))
        self.assertFalse(ConfigAuditLog.objects.exists())

    def test_unknown_account_and_invalid_body(self):
        self.assertEqual(self.change('nadie', False).status_code, 404)
        self.assertEqual(self.change('a.b', False).status_code, 400)
        response = self.panel.patch(reverse('accounts:admin-account-status', kwargs={'uid': CLIENT}),
                                    {'reason': 'x'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ConfigAuditLog.objects.exists())

    def test_profile_without_auth_user_is_still_suspended(self):
        from firebase_admin import auth as real_auth
        self.auth.update_user.side_effect = real_auth.UserNotFoundError('sin usuario')

        self.assertEqual(self.change(CLIENT, False).status_code, 200)
        self.assertFalse(self.fb.get_data(f"User/Clientes/{CLIENT}/isActive"))

    def test_only_the_panel_can_change_it(self):
        # El token de la app no sirve en las rutas del panel
        self.assertIn(self.change(CLIENT, False, client=self.api(CLIENT)).status_code, (401, 403))
        self.assertEqual(self.change(CLIENT, False, client=APIClient()).status_code, 401)
        self.auth.update_user.assert_not_called()

    def test_panel_lists_show_is_active(self):
        self.fb.update_data(f"User/Clientes/{CLIENT}", {'isActive': False})
        with mock.patch('worker_verification.services.client_service.client_service.firebase', self.fb), \
                mock.patch('worker_verification.services.worker_service.worker_service.firebase', self.fb):
            clients = self.panel.get('/api/clients/').data['data']
            client = self.panel.get(f'/api/clients/{CLIENT}/').data['data']
            worker = self.panel.get(f'/api/workers/{WORKER}/').data['data']
        self.assertEqual({c['id']: c['isActive'] for c in clients}[CLIENT], False)
        self.assertFalse(client['isActive'])
        # Sin el campo cuenta como activa
        self.assertTrue(worker['isActive'])

    def test_suspended_request_does_not_touch_other_request(self):
        self.change(CLIENT, False)
        # La solicitud pendiente del cliente se cancela; req-2 es de otro cliente
        self.assertEqual(self.request_data()['status'], 'cancelled')
        self.assertEqual(self.fb.get_data('requests/req-2')['status'], 'accepted')
        self.assertIn(('fcm-worker', 'request_cancelled'), self.sent_notifications())
