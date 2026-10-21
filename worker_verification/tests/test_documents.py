from unittest import mock

from payments.tests.fakes import app_token, patch_verify_id_token

from ..models import VerificationLog
from ..services.document_service import document_service
from .base import ANA, BETO, CARO, PanelTestCase

DOCS = '/api/documents/'


def new_document(**overrides):
    body = {'id': 'hv-caro', 'workerId': CARO, 'documentType': 'hoja_de_vida', 'category': 'hojaDeVida',
            'fileName': 'cv.pdf', 'fileUrl': 'https://storage.test/cv.pdf', 'fileType': 'application/pdf',
            'fileSize': 204800}
    body.update(overrides)
    return body


class DocumentQueryTests(PanelTestCase):
    """Consultas del panel sobre WorkerDocuments (verificación documental)."""

    def test_pending_lists_every_pending_document_with_its_location(self):
        response = self.client.get(f'{DOCS}pending/')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['count'], 3)
        found = {(doc['workerId'], doc['category'], doc['id']) for doc in body['data']}
        self.assertEqual(found, {(BETO, 'hojaDeVida', 'hv-beto'),
                                 (BETO, 'certificaciones', 'c1'), (BETO, 'certificaciones', 'c2')})

    def test_pending_is_empty_without_documents(self):
        self.fb.set_data('WorkerDocuments', None)
        self.assertEqual(self.client.get(f'{DOCS}pending/').json()['count'], 0)

    def test_worker_documents_by_category(self):
        self.assertIn('hojaDeVida', self.client.get(f'{DOCS}worker/{ANA}/').json()['data'])
        self.assertEqual(self.client.get(f'{DOCS}worker/{CARO}/').json()['data'], {})

        self.assertEqual(self.client.get(f'{DOCS}worker/{ANA}/hoja-vida/').json()['data']['id'], 'hv-ana')
        self.assertEqual(self.client.get(f'{DOCS}worker/{ANA}/antecedentes/').status_code, 200)
        self.assertEqual(list(self.client.get(f'{DOCS}worker/{ANA}/titulos/').json()['data']), ['t1'])
        self.assertEqual(len(self.client.get(f'{DOCS}worker/{BETO}/cartas/').json()['data']), 3)

    def test_missing_mandatory_documents_are_404_and_optional_are_empty(self):
        self.assertEqual(self.client.get(f'{DOCS}worker/{CARO}/hoja-vida/').status_code, 404)
        self.assertEqual(self.client.get(f'{DOCS}worker/{CARO}/antecedentes/').status_code, 404)
        self.assertEqual(self.client.get(f'{DOCS}worker/{CARO}/titulos/').json()['data'], {})
        self.assertEqual(self.client.get(f'{DOCS}worker/{CARO}/cartas/').json()['data'], {})

    def test_firebase_error_is_500(self):
        with mock.patch.object(self.fb, 'get_data', side_effect=Exception('caído')):
            for path in ('pending/', f'worker/{ANA}/', f'worker/{ANA}/hoja-vida/', f'worker/{ANA}/titulos/',
                         f'worker/{ANA}/check-requirements/'):
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(f'{DOCS}{path}').status_code, 500)

    def test_signed_file_url(self):
        response = self.client.get(f'{DOCS}file-url/', {
            'workerId': BETO, 'category': 'certificaciones', 'subcategory': 'cartasRecomendacion',
            'filename': 'carta.pdf'})
        self.assertEqual(response.json()['url'], 'https://storage.test/firmada')
        self.fb.get_file_url.assert_called_with(f'worker_documents/{BETO}/certificaciones/cartasRecomendacion/carta.pdf')

        self.client.get(f'{DOCS}file-url/', {'workerId': ANA, 'category': 'hojaDeVida', 'filename': 'cv.pdf'})
        self.fb.get_file_url.assert_called_with(f'worker_documents/{ANA}/hojaDeVida/cv.pdf')

        self.assertEqual(self.client.get(f'{DOCS}file-url/', {'workerId': ANA}).status_code, 400)


class RequirementsTests(PanelTestCase):
    """Documentos completos: hoja de vida y antecedentes, más un título o al menos tres cartas."""

    def check(self, uid):
        response = self.client.get(f'{DOCS}worker/{uid}/check-requirements/')
        self.assertEqual(response.status_code, 200)
        return response.json()['data']

    def test_with_title(self):
        data = self.check(ANA)
        self.assertEqual((data['hasHojaVida'], data['hasAntecedentes'], data['hasTitulo'], data['isComplete']),
                         (True, True, True, True))

    def test_with_three_letters_and_no_title(self):
        data = self.check(BETO)
        self.assertEqual((data['hasTitulo'], data['cartasCount'], data['hasMinimumCartas'], data['isComplete']),
                         (False, 3, True, True))
        # El servicio usa la misma regla que la respuesta (antes exigía título y cartas)
        self.assertTrue(document_service.has_all_required_documents(BETO)['isComplete'])

    def test_two_letters_are_not_enough(self):
        self.fb.set_data(f'WorkerDocuments/{BETO}/certificaciones/cartasRecomendacion/c3', None)
        data = self.check(BETO)
        self.assertEqual((data['cartasCount'], data['isComplete']), (2, False))

    def test_without_documents(self):
        data = self.check(CARO)
        self.assertFalse(any(data[key] for key in ('hasHojaVida', 'hasAntecedentes', 'hasTitulo', 'isComplete')))

    def test_mandatory_documents_are_required(self):
        self.fb.set_data(f'WorkerDocuments/{ANA}/antecedentesJudiciales', None)
        self.assertFalse(self.check(ANA)['isComplete'])


class DocumentWriteTests(PanelTestCase):

    def test_create_mandatory_document(self):
        response = self.client.post(DOCS, new_document(), format='json')
        self.assertEqual(response.status_code, 201)
        stored = self.fb.get_data(f'WorkerDocuments/{CARO}/hojaDeVida')
        self.assertEqual((stored['status'], stored['reviewedAt'], stored['workerId']), ('pending', 0, CARO))
        self.assertIsInstance(stored['uploadedAt'], int)

    def test_create_certification_goes_under_its_subcategory(self):
        response = self.client.post(DOCS, new_document(
            id='t9', documentType='titulo', category='certificaciones', subcategory='titulos'), format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.fb.get_data(f'WorkerDocuments/{CARO}/certificaciones/titulos/t9')['status'], 'pending')

    def test_create_validates_type_and_size(self):
        for body in (new_document(fileType='application/zip'), new_document(fileSize=10 * 1024 * 1024 + 1),
                     new_document(id=None)):
            with self.subTest(body=body):
                self.assertEqual(self.client.post(DOCS, body, format='json').status_code, 400)
        self.assertIsNone(self.fb.get_data(f'WorkerDocuments/{CARO}'))

    def test_approve_and_reject_write_the_decision(self):
        response = self.client.post(f'{DOCS}approve/', {
            'workerId': BETO, 'category': 'certificaciones', 'subcategory': 'cartasRecomendacion',
            'documentId': 'c1'}, format='json')
        self.assertEqual(response.status_code, 200)
        approved = self.fb.get_data(f'WorkerDocuments/{BETO}/certificaciones/cartasRecomendacion/c1')
        self.assertEqual((approved['status'], approved['reviewedBy']), ('approved', 'revisora'))
        self.assertGreater(approved['reviewedAt'], 0)

        response = self.client.post(f'{DOCS}reject/', {
            'workerId': BETO, 'category': 'hojaDeVida', 'documentId': 'hv-beto',
            'reason': '  La hoja de vida no tiene firma  '}, format='json')
        self.assertEqual(response.status_code, 200)
        rejected = self.fb.get_data(f'WorkerDocuments/{BETO}/hojaDeVida')
        self.assertEqual((rejected['status'], rejected['rejectionReason']), ('rejected', 'La hoja de vida no tiene firma'))
        self.assertEqual(VerificationLog.objects.count(), 2)

    def test_reject_requires_a_real_reason_and_the_document_location(self):
        cases = [
            (f'{DOCS}reject/', {'workerId': BETO, 'category': 'hojaDeVida', 'documentId': 'x', 'reason': 'corta'}),
            (f'{DOCS}reject/', {'workerId': BETO, 'category': 'hojaDeVida', 'documentId': 'x', 'reason': ' ' * 12}),
            (f'{DOCS}reject/', {'category': 'hojaDeVida', 'documentId': 'x', 'reason': 'Motivo suficiente'}),
            (f'{DOCS}approve/', {'workerId': BETO, 'documentId': 'x'}),
        ]
        for url, body in cases:
            with self.subTest(body=body):
                self.assertEqual(self.client.post(url, body, format='json').status_code, 400)
        self.assertEqual(self.fb.get_data(f'WorkerDocuments/{BETO}/hojaDeVida')['status'], 'pending')
        self.assertFalse(VerificationLog.objects.exists())

    def test_delete_document(self):
        response = self.client.delete(f'{DOCS}delete/', {
            'workerId': BETO, 'category': 'certificaciones', 'subcategory': 'cartasRecomendacion',
            'documentId': 'c2'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.fb.get_data(f'WorkerDocuments/{BETO}/certificaciones/cartasRecomendacion/c2'))
        self.assertIsNotNone(self.fb.get_data(f'WorkerDocuments/{BETO}/certificaciones/cartasRecomendacion/c1'))

        self.assertEqual(self.client.delete(f'{DOCS}delete/', {'workerId': BETO}, format='json').status_code, 400)


class DocumentAccessTests(PanelTestCase):

    def test_requires_panel_session(self):
        self.client.credentials()
        self.assertEqual(self.client.get(f'{DOCS}pending/').status_code, 401)

        # Un ID token de la app (RS256) no sirve en las rutas del panel
        with patch_verify_id_token():
            self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {app_token(ANA)}')
            self.assertEqual(self.client.post(f'{DOCS}approve/', {
                'workerId': ANA, 'category': 'hojaDeVida', 'documentId': 'hv-ana'}, format='json').status_code, 401)
