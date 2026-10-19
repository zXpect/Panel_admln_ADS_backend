from datetime import date
from unittest import mock

from .base import CLIENT, PanelTestCase

CLIENTS = '/api/clients/'
DASHBOARD = '/api/dashboard/'


class ClientTests(PanelTestCase):
    """Consulta de clientes desde el panel (solo lectura)."""

    def test_list_search_detail_and_count(self):
        response = self.client.get(CLIENTS)
        self.assertEqual((response.status_code, response.json()['count']), (200, 2))
        self.assertEqual([c['id'] for c in self.client.get(CLIENTS, {'search': 'carla@'}).json()['data']], [CLIENT])
        self.assertEqual(self.client.get(CLIENTS, {'search': 'mora'}).json()['count'], 1)
        self.assertEqual(self.client.get(f'{CLIENTS}{CLIENT}/').json()['data']['name'], 'Carla')
        self.assertEqual(self.client.get(f'{CLIENTS}no-existe/').status_code, 404)
        self.assertEqual(self.client.get(f'{CLIENTS}count/').json()['count'], 2)

    def test_without_clients(self):
        self.fb.set_data('User/Clientes', None)
        self.assertEqual(self.client.get(CLIENTS).json()['count'], 0)
        self.assertEqual(self.client.get(f'{CLIENTS}count/').json()['count'], 0)

    def test_firebase_error_is_500(self):
        with mock.patch.object(self.fb, 'get_data', side_effect=Exception('caído')):
            for path in ('', f'{CLIENT}/', 'count/'):
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(f'{CLIENTS}{path}').status_code, 500)


class DashboardTests(PanelTestCase):

    def test_stats(self):
        response = self.client.get(f'{DASHBOARD}stats/')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['workers'], {'total': 3, 'verified': 1, 'available': 2, 'online': 1,
                                           'byCategory': {'plomeria': 1, 'electricidad': 1, 'pintura': 1}})
        self.assertEqual(data['clients'], {'total': 2})
        documents = data['documents']
        self.assertEqual((documents['total'], documents['pending'], documents['approved'], documents['rejected'],
                          documents['processed']), (8, 3, 4, 1, 5))
        self.assertEqual(documents['pendingByType'],
                         {'hojaDeVida': 1, 'antecedentesJudiciales': 0, 'titulos': 0, 'cartasRecomendacion': 2})

    def test_activity_windows(self):
        activity = self.client.get(f'{DASHBOARD}activity-stats/').json()['data']
        # Ana tuvo actividad hoy, Beto hace 3 días y Caro hace 40 días
        self.assertEqual((activity['workers']['active_24h'], activity['workers']['active_7d'],
                          activity['workers']['active_30d']), (1, 2, 2))
        self.assertEqual((activity['documents']['processed_24h'], activity['documents']['uploaded_24h']), (5, 8))

    def test_weekly_and_monthly_trends(self):
        weekly = self.client.get(f'{DASHBOARD}weekly-trends/').json()['data']
        self.assertEqual(len(weekly['trends']), 7)
        self.assertEqual(weekly['trends'][-1]['date'], date.today().isoformat())
        self.assertEqual((weekly['summary']['totalDocsUploaded'], weekly['summary']['totalDocsProcessed']), (8, 5))

        monthly = self.client.get(f'{DASHBOARD}monthly-trends/').json()['data']
        self.assertEqual(sum(week['documentsUploaded'] for week in monthly['trends']), 8)

    def test_empty_database(self):
        self.fb.data = {}
        data = self.client.get(f'{DASHBOARD}stats/').json()['data']
        self.assertEqual((data['workers']['total'], data['clients']['total'], data['documents']['total']), (0, 0, 0))
        weekly = self.client.get(f'{DASHBOARD}weekly-trends/').json()['data']
        self.assertEqual(weekly['summary']['totalWorkersActive'], 0)

    def test_trends_fall_back_to_zeros_when_firebase_fails(self):
        with mock.patch.object(self.fb, 'get_data', side_effect=Exception('caído')):
            weekly = self.client.get(f'{DASHBOARD}weekly-trends/')
            self.assertEqual(weekly.status_code, 200)
            self.assertEqual(len(weekly.json()['data']['trends']), 7)
            self.assertEqual(self.client.get(f'{DASHBOARD}stats/').status_code, 500)
