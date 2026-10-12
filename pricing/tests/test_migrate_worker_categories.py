from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from payments.tests.fakes import FakeFirebase

WORKERS = {
    'w1': {'name': 'Ana', 'work': 'Plomería'},
    'w2': {'name': 'Luis', 'work': 'Electricista'},
    'w3': {'name': 'Rosa', 'work': 'carpintero '},
    'w4': {'name': 'Juan', 'work': 'Ferretería'},
    'w5': {'name': 'Eva', 'work': 'Pintor', 'categories': ['pintura', 'albanileria']},
    'w6': {'name': 'Sin oficio'},
}


class MigrateWorkerCategoriesTests(TestCase):

    def setUp(self):
        self.fb = FakeFirebase({'User': {'Trabajadores': WORKERS}})
        patcher = mock.patch('pricing.management.commands.migrate_worker_categories.firebase_service', self.fb)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_command(self, *args):
        out = StringIO()
        call_command('migrate_worker_categories', *args, stdout=out)
        return out.getvalue()

    def categories(self, uid):
        return self.fb.get_data(f"User/Trabajadores/{uid}/categories")

    def test_dry_run_writes_nothing(self):
        output = self.run_command('--dry-run')
        self.assertIn('Convertidos: 3', output)
        self.assertIn('Revisión manual: 2', output)
        self.assertIn('Ferretería', output)
        self.assertIsNone(self.categories('w1'))

    def test_converts_work_and_keeps_it(self):
        self.run_command()
        self.assertEqual(self.categories('w1'), ['plomeria'])
        self.assertEqual(self.categories('w2'), ['electricidad'])
        self.assertEqual(self.categories('w3'), ['carpinteria'])
        self.assertEqual(self.fb.get_data('User/Trabajadores/w1/work'), 'Plomería')
        # Sin equivalencia y ya migrados: sin cambios
        self.assertIsNone(self.categories('w4'))
        self.assertIsNone(self.categories('w6'))
        self.assertEqual(self.categories('w5'), ['pintura', 'albanileria'])

    def test_is_idempotent(self):
        self.run_command()
        self.assertIn('Convertidos: 0 · Ya tenían categories: 4', self.run_command())
