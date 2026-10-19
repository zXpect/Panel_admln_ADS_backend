from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from ..models import VerificationLog
from ..services.document_service import document_service
from ..services.worker_service import worker_service

WORKER = 'worker-1'
APPROVE_URL = '/api/documents/approve/'
REJECT_URL = '/api/documents/reject/'
STATUS_URL = f'/api/workers/{WORKER}/verification_status/'
REASON = 'El certificado tiene más de tres meses de expedido'


class VerificationAuditTestBase(TestCase):
    """Panel autenticado con un JWT real de simplejwt y Firebase simulado"""

    def setUp(self):
        self.admin = User.objects.create_user('revisora', password='x')
        # Otro administrador cuyo id intentaría usurparse con reviewerId
        self.other_admin = User.objects.create_user('otro', password='x')

        self.client = APIClient()
        token = RefreshToken.for_user(self.admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        self.firebase = mock.MagicMock()
        self.firebase.get_data.return_value = {
            'name': 'Ana',
            'verificationStatus': {'status': 'documents_submitted', 'submittedAt': 1},
        }
        for service in (document_service, worker_service):
            patcher = mock.patch.object(service, 'firebase', self.firebase)
            patcher.start()
            self.addCleanup(patcher.stop)

    def written(self):
        """(ruta, datos) de la última escritura en Firebase"""
        return self.firebase.update_data.call_args.args


class DocumentDecisionAuditTests(VerificationAuditTestBase):

    def test_approve_logs_authenticated_reviewer_and_ignores_body_reviewer_id(self):
        response = self.client.post(APPROVE_URL, {
            'workerId': WORKER, 'category': 'hojaDeVida', 'subcategory': None,
            'documentId': 'doc-01', 'reviewerId': str(self.other_admin.pk),
        }, format='json')

        self.assertEqual(response.status_code, 200)
        log = VerificationLog.objects.get()
        self.assertEqual(log.reviewer, self.admin)
        self.assertEqual(log.worker_id, WORKER)
        self.assertEqual(log.document_type, 'hojaDeVida')
        self.assertEqual(log.action, 'approved')
        self.assertIsNone(log.reason)
        self.assertIsNotNone(log.created_at)

        path, data = self.written()
        self.assertEqual(path, f'WorkerDocuments/{WORKER}/hojaDeVida')
        self.assertEqual(data['reviewedBy'], 'revisora')
        self.assertEqual(data['status'], 'approved')

    def test_approve_without_reviewer_id_is_accepted(self):
        response = self.client.post(APPROVE_URL, {
            'workerId': WORKER, 'category': 'certificaciones', 'subcategory': 'titulos',
            'documentId': 'doc-02',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        log = VerificationLog.objects.get()
        self.assertEqual(log.reviewer, self.admin)
        self.assertEqual(log.document_type, 'certificaciones/titulos')
        path, _ = self.written()
        self.assertEqual(path, f'WorkerDocuments/{WORKER}/certificaciones/titulos/doc-02')

    def test_reject_logs_reason_and_authenticated_reviewer(self):
        response = self.client.post(REJECT_URL, {
            'workerId': WORKER, 'category': 'antecedentesJudiciales', 'subcategory': None,
            'documentId': 'doc-03', 'reviewerId': 'admin', 'reason': REASON,
        }, format='json')

        self.assertEqual(response.status_code, 200)
        log = VerificationLog.objects.get()
        self.assertEqual(log.reviewer, self.admin)
        self.assertEqual(log.action, 'rejected')
        self.assertEqual(log.document_type, 'antecedentesJudiciales')
        self.assertEqual(log.reason, REASON)

        _, data = self.written()
        self.assertEqual(data['reviewedBy'], 'revisora')
        self.assertEqual(data['rejectionReason'], REASON)

    def test_invalid_rejection_writes_nothing(self):
        response = self.client.post(REJECT_URL, {
            'workerId': WORKER, 'category': 'hojaDeVida', 'documentId': 'doc-04', 'reason': 'corta',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertFalse(VerificationLog.objects.exists())
        self.firebase.update_data.assert_not_called()

    def test_firebase_error_returns_generic_500_and_rolls_back_log(self):
        self.firebase.update_data.side_effect = RuntimeError('secreto: credencial interna')

        with self.assertLogs('worker_verification.views.document_views', level='ERROR') as logs:
            response = self.client.post(APPROVE_URL, {
                'workerId': WORKER, 'category': 'hojaDeVida', 'documentId': 'doc-05',
            }, format='json')

        self.assertEqual(response.status_code, 500)
        self.assertNotIn('secreto', response.content.decode())
        self.assertIn('secreto', '\n'.join(logs.output))
        self.assertFalse(VerificationLog.objects.exists())

    def test_requires_authentication(self):
        response = APIClient().post(APPROVE_URL, {
            'workerId': WORKER, 'category': 'hojaDeVida', 'documentId': 'doc-06',
        }, format='json')

        self.assertEqual(response.status_code, 401)
        self.assertFalse(VerificationLog.objects.exists())
        self.firebase.update_data.assert_not_called()


class WorkerVerificationStatusAuditTests(VerificationAuditTestBase):

    def test_status_change_logs_authenticated_reviewer(self):
        response = self.client.patch(STATUS_URL, {'status': 'approved'}, format='json')

        self.assertEqual(response.status_code, 200)
        log = VerificationLog.objects.get()
        self.assertEqual(log.reviewer, self.admin)
        self.assertEqual(log.worker_id, WORKER)
        self.assertEqual(log.document_type, 'verificationStatus')
        self.assertEqual(log.action, 'approved')

        _, data = self.written()
        self.assertEqual(data['verificationStatus'], {'status': 'approved', 'submittedAt': 1})

    def test_documents_submitted_is_logged_as_pending(self):
        response = self.client.patch(STATUS_URL, {'status': 'documents_submitted'}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(VerificationLog.objects.get().action, 'pending')

    def test_unknown_worker_returns_404_without_log(self):
        self.firebase.get_data.return_value = None

        response = self.client.patch(STATUS_URL, {'status': 'rejected'}, format='json')

        self.assertEqual(response.status_code, 404)
        self.assertFalse(VerificationLog.objects.exists())

    def test_firebase_error_returns_generic_500_and_rolls_back_log(self):
        self.firebase.update_data.side_effect = RuntimeError('secreto: ruta interna')

        with self.assertLogs('worker_verification.views.worker_views', level='ERROR'):
            response = self.client.patch(STATUS_URL, {'status': 'rejected'}, format='json')

        self.assertEqual(response.status_code, 500)
        self.assertNotIn('secreto', response.content.decode())
        self.assertFalse(VerificationLog.objects.exists())
