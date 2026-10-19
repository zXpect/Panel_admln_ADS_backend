import io
from types import SimpleNamespace
from unittest import mock

import pandas as pd
from django.core.files.uploadedfile import SimpleUploadedFile
from firebase_admin import auth

from .base import ANA, PanelTestCase

UPLOAD = '/api/workers/bulk-upload/'
AUTH = 'worker_verification.services.bulk_worker_service.auth'


def excel(rows, name='trabajadores.xlsx'):
    buffer = io.BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False)
    return SimpleUploadedFile(name, buffer.getvalue(),
                              content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def row(email, **extra):
    data = {'Nombre': 'Luis', 'Apellido': 'Paz', 'Email': email, 'Telefono': 3105551234.0, 'Categoria': 'Pintor'}
    data.update(extra)
    return data


class BulkUploadTests(PanelTestCase):
    """Carga masiva de trabajadores desde Excel (panel)."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch(AUTH)
        self.auth = patcher.start()
        self.addCleanup(patcher.stop)
        self.auth.EmailAlreadyExistsError = auth.EmailAlreadyExistsError
        self.created = 0

        def create_user(email, **kwargs):
            if email == 'ana@ads.test':
                raise auth.EmailAlreadyExistsError('ya existe', None, None)
            self.created += 1
            return SimpleNamespace(uid=f'bulk-{self.created}')

        self.auth.create_user.side_effect = create_user
        self.auth.get_user_by_email.return_value = SimpleNamespace(uid=ANA)

    def upload(self, file):
        return self.client.post(UPLOAD, {'file': file}, format='multipart')

    def test_valid_rows_create_auth_users_and_profiles(self):
        response = self.upload(excel([row('luis@ads.test'), row('marta@ads.test', Nombre='Marta')]))

        self.assertEqual(response.status_code, 201)
        data = response.json()['data']
        self.assertEqual((data['total_processed'], data['successful'], data['failed']), (2, 2, 0))
        profile = self.worker('bulk-1')
        # El teléfono queda como texto (la app lo lee como String) y no queda disponible sin documentos
        self.assertEqual((profile['phone'], profile['work'], profile['isAvailable']), ('3105551234', 'Pintor', False))
        self.assertNotIn('password', profile)
        self.assertEqual(len(data['success_details'][0]['password']), 12)

    def test_email_of_an_existing_account_is_reported_and_left_untouched(self):
        response = self.upload(excel([row('ana@ads.test'), row('luis@ads.test')]))

        self.assertEqual(response.status_code, 207)
        data = response.json()['data']
        self.assertEqual((data['successful'], data['failed']), (1, 1))
        self.assertIn('ya pertenece a una cuenta de ADS', data['error_details'][0]['error'])
        # Antes se sobrescribía el perfil de Ana
        self.assertEqual(self.worker(ANA)['name'], 'Ana')
        self.auth.delete_user.assert_not_called()

    def test_profile_failure_only_rolls_back_new_auth_users(self):
        self.auth.get_user_by_email.return_value = SimpleNamespace(uid='cuenta-sin-perfil')
        with mock.patch.object(self.fb, 'set_data', side_effect=Exception('caído')):
            response = self.upload(excel([row('nuevo@ads.test'), row('ana@ads.test')]))

        self.assertEqual(response.status_code, 400)
        # Solo se borra la cuenta recién creada; la que ya existía es de otra persona
        self.auth.delete_user.assert_called_once_with('bulk-1')

    def test_invalid_files(self):
        self.assertEqual(self.client.post(UPLOAD, {}, format='multipart').status_code, 400)
        self.assertEqual(self.upload(SimpleUploadedFile('lista.csv', b'a,b')).status_code, 400)
        response = self.upload(excel([{'Nombre': 'Luis', 'Email': 'luis@ads.test'}]))
        self.assertEqual(response.status_code, 400)
        self.assertIn('Columnas faltantes', response.json()['error'])
        self.auth.create_user.assert_not_called()

    def test_auth_error_is_reported_per_row(self):
        self.auth.create_user.side_effect = Exception('cuota excedida')
        response = self.upload(excel([row('luis@ads.test')]))
        self.assertEqual(response.status_code, 400)
        self.assertIn('cuota excedida', response.json()['data']['error_details'][0]['error'])

    def test_template_download(self):
        response = self.client.get('/api/workers/bulk-upload-template/')
        self.assertEqual(response.status_code, 200)
        columns = pd.read_excel(io.BytesIO(response.content)).columns.str.lower()
        for column in ('nombre', 'apellido', 'email', 'telefono', 'categoria'):
            self.assertIn(column, columns)
