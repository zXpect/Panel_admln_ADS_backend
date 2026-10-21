import time
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from payments.tests.fakes import FakeFirebase

from ..services.bulk_worker_service import bulk_worker_service
from ..services.client_service import client_service
from ..services.dashboard_service import dashboard_service
from ..services.document_service import document_service
from ..services.worker_service import worker_service

DAY_MS = 24 * 60 * 60 * 1000

# Trabajadores: Ana verificada y completa; Beto con documentos en revisión; Caro sin documentos
ANA, BETO, CARO = 'worker-ana', 'worker-beto', 'worker-caro'
CLIENT = 'client-1'


def now_ms():
    return int(time.time() * 1000)


def document(status='pending', uploaded=None, reviewed=0, **extra):
    data = {
        'id': extra.pop('id', 'doc'), 'documentType': extra.pop('documentType', 'hoja_de_vida'),
        'fileName': 'archivo.pdf', 'fileType': 'application/pdf', 'fileSize': 1024,
        'status': status, 'uploadedAt': uploaded if uploaded is not None else now_ms(), 'reviewedAt': reviewed,
    }
    data.update(extra)
    return data


def initial_data():
    now = now_ms()
    return {
        'User': {
            'Trabajadores': {
                ANA: {'name': 'Ana', 'lastName': 'Rojas', 'email': 'ana@ads.test', 'phone': '3001112233',
                      'work': 'Plomería', 'categories': ['plomeria'], 'isAvailable': True, 'isOnline': True,
                      'rating': 4.5, 'totalRatings': 2, 'timestamp': now,
                      'verificationStatus': {'status': 'approved', 'timestamp': now}},
                BETO: {'name': 'Beto', 'lastName': 'Gil', 'email': 'beto@ads.test', 'phone': '3002223344',
                       'work': 'Electricista', 'isAvailable': True, 'isOnline': False,
                       'rating': 0, 'totalRatings': 0, 'timestamp': now - 3 * DAY_MS,
                       'verificationStatus': {'status': 'documents_submitted', 'timestamp': now}},
                CARO: {'name': 'Caro', 'lastName': 'Díaz', 'email': 'caro@ads.test', 'phone': '3003334455',
                       'work': 'Pintor', 'isAvailable': False, 'isOnline': False,
                       'rating': 0, 'totalRatings': 0, 'timestamp': now - 40 * DAY_MS},
            },
            'Clientes': {
                CLIENT: {'name': 'Carla', 'lastName': 'Ruiz', 'email': 'carla@ads.test', 'phone': '3109998877'},
                'client-2': {'name': 'Pedro', 'lastName': 'Mora', 'email': 'pedro@ads.test', 'phone': '3108887766'},
            },
        },
        'WorkerDocuments': {
            ANA: {
                'hojaDeVida': document('approved', reviewed=now, id='hv-ana'),
                'antecedentesJudiciales': document('approved', reviewed=now, id='ant-ana',
                                                   documentType='antecedentes_judiciales'),
                'certificaciones': {'titulos': {'t1': document('approved', reviewed=now, id='t1',
                                                               documentType='titulo')}},
            },
            BETO: {
                'hojaDeVida': document('pending', id='hv-beto'),
                'antecedentesJudiciales': document('rejected', reviewed=now, id='ant-beto',
                                                   documentType='antecedentes_judiciales',
                                                   rejectionReason='Documento ilegible'),
                'certificaciones': {'cartasRecomendacion': {
                    'c1': document('pending', id='c1', documentType='carta_recomendacion'),
                    'c2': document('pending', id='c2', documentType='carta_recomendacion'),
                    'c3': document('approved', reviewed=now, id='c3', documentType='carta_recomendacion'),
                }},
            },
        },
    }


class PanelTestCase(TestCase):
    """Panel autenticado con un JWT real y Firebase en memoria compartido por los servicios."""

    def setUp(self):
        cache.clear()  # contadores de throttling
        self.admin = User.objects.create_user('revisora', password='x')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(self.admin).access_token}')

        self.fb = FakeFirebase(initial_data())
        self.fb.get_file_url = mock.Mock(return_value='https://storage.test/firmada')
        for service in (document_service, worker_service, client_service, dashboard_service, bulk_worker_service):
            patcher = mock.patch.object(service, 'firebase', self.fb)
            patcher.start()
            self.addCleanup(patcher.stop)

    def worker(self, uid):
        return self.fb.get_data(f'User/Trabajadores/{uid}')
