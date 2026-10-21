from unittest import mock

from django.urls import reverse

from accounts.services.account_service import account_service
from payments.tests.test_api import CLIENT, REQ, WORKER, AppApiTestCase


class DeleteAccountTests(AppApiTestCase):
    """DELETE /api/me/ (D18): supresión de datos por el propio usuario."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(account_service, 'firebase', self.fb)
        patcher.start()
        self.addCleanup(patcher.stop)
        delete_user = mock.patch('accounts.services.account_service.firebase_auth.delete_user')
        self.delete_user = delete_user.start()
        self.addCleanup(delete_user.stop)

        self.set_request(status='completed', client_name='Carla', client_phone='300', client_email='c@x.co',
                         payment_status='approved')
        self.fb.set_data('requests/req-2', {'client_id': CLIENT, 'worker_id': WORKER, 'worker_name': 'Ana',
                                            'client_name': 'Carla', 'status': 'pending'})
        self.fb.set_data('requests/req-3', {'client_id': 'otro-cliente', 'worker_id': WORKER,
                                            'client_name': 'Pedro', 'status': 'pending'})
        self.fb.set_data(f"User/Clientes/{CLIENT}", {'name': 'Carla', 'email': 'c@x.co'})
        self.fb.set_data(f"notifications/{CLIENT}/n1", {'title': 'x'})
        self.fb.files = [f"client_images/{CLIENT}/foto.jpg", f"worker_documents/{WORKER}/hoja.pdf",
                         f"worker_profiles/profile_{WORKER}_1.jpg"]

    def delete(self, uid=CLIENT):
        return self.api(uid).delete(reverse('accounts:me'))

    def test_client_account_is_deleted_and_requests_anonymized(self):
        response = self.delete()

        self.assertEqual(response.status_code, 204)
        self.delete_user.assert_called_once_with(CLIENT)
        for path in (f"User/Clientes/{CLIENT}", f"Tokens/{CLIENT}", f"notifications/{CLIENT}"):
            self.assertIsNone(self.fb.get_data(path), path)
        self.assertEqual(self.fb.files, [f"worker_documents/{WORKER}/hoja.pdf",
                                         f"worker_profiles/profile_{WORKER}_1.jpg"])

        done = self.request_data()
        self.assertEqual((done['client_name'], done['client_phone'], done['client_email']),
                         ('Usuario eliminado', '', ''))
        self.assertEqual((done['status'], done['client_id']), ('completed', CLIENT))

        pending = self.fb.get_data('requests/req-2')
        self.assertEqual((pending['status'], pending['cancelled_by'], pending['client_name']),
                         ('cancelled', 'client', 'Usuario eliminado'))
        self.assertIn(('fcm-worker', 'request_cancelled'), self.sent_notifications())
        # La solicitud de otro cliente no se toca
        self.assertEqual(self.fb.get_data('requests/req-3')['client_name'], 'Pedro')

    def test_worker_account_deletes_documents_and_location(self):
        self.fb.set_data(f"User/Trabajadores/{WORKER}", {'name': 'Ana'})
        self.fb.set_data(f"active_workers/{WORKER}", {'g': 'x'})
        self.fb.set_data(f"WorkerDocuments/{WORKER}", {'hojaDeVida': {'status': 'approved'}})

        self.assertEqual(self.delete(WORKER).status_code, 204)

        for path in (f"User/Trabajadores/{WORKER}", f"active_workers/{WORKER}", f"WorkerDocuments/{WORKER}"):
            self.assertIsNone(self.fb.get_data(path), path)
        self.assertEqual(self.fb.files, [f"client_images/{CLIENT}/foto.jpg"])
        self.assertEqual(self.request_data()['worker_name'], 'Usuario eliminado')
        self.assertEqual(self.fb.get_data('requests/req-3')['status'], 'cancelled')
        self.assertIn(('fcm-client', 'request_cancelled'), self.sent_notifications())

    def test_active_service_blocks_deletion(self):
        self.set_request(status='in_progress')

        response = self.delete()

        self.assertEqual(response.status_code, 409)
        self.delete_user.assert_not_called()
        self.assertIsNotNone(self.fb.get_data(f"User/Clientes/{CLIENT}"))
        self.assertEqual(self.fb.get_data('requests/req-2')['status'], 'pending')

    def test_auth_failure_returns_500_so_user_can_retry(self):
        self.delete_user.side_effect = Exception('auth caído')
        self.assertEqual(self.delete().status_code, 500)

    def test_requires_app_token(self):
        self.assertEqual(self.api().delete(reverse('accounts:me')).status_code, 401)
