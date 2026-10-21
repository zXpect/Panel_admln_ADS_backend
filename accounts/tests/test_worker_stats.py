from unittest import mock

from django.urls import reverse

from payments.tests.test_api import CLIENT, WORKER, AppApiTestCase


class WorkerStatsTests(AppApiTestCase):
    """GET /api/workers/<id>/stats/ (B12)."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch('accounts.views.firebase_service', self.fb)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.set_request(status='completed', is_rated=False)
        self.fb.set_data('requests/req-2', {'client_id': CLIENT, 'worker_id': WORKER, 'status': 'completed'})
        self.fb.set_data('requests/req-3', {'client_id': CLIENT, 'worker_id': WORKER, 'status': 'cancelled'})
        self.fb.set_data('requests/req-4', {'client_id': CLIENT, 'worker_id': 'otro', 'status': 'completed'})

    def stats(self, worker_id=WORKER, uid=CLIENT):
        return self.api(uid).get(reverse('accounts:worker-stats', kwargs={'worker_id': worker_id}))

    def test_counts_completed_jobs_rated_or_not(self):
        response = self.stats()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data'], {
            'worker_id': WORKER, 'completed_jobs': 2, 'rating': 4.0, 'total_ratings': 2})

    def test_unknown_or_invalid_worker(self):
        self.assertEqual(self.stats('no-existe').status_code, 404)
        self.assertEqual(self.stats('a.b').status_code, 400)

    def test_requires_app_token(self):
        self.assertEqual(self.api().get(reverse('accounts:worker-stats', kwargs={'worker_id': WORKER})).status_code,
                         401)
