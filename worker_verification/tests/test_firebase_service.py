from unittest import mock

from django.test import SimpleTestCase

from ..services.firebase_service import FirebaseService, firebase_service

MODULE = 'worker_verification.services.firebase_service'


class FirebaseServiceTests(SimpleTestCase):
    """Capa base sobre el SDK de Firebase: sin red, con el SDK simulado."""

    def setUp(self):
        db = mock.patch(f'{MODULE}.db')
        storage = mock.patch(f'{MODULE}.storage')
        self.db = db.start()
        self.storage = storage.start()
        self.addCleanup(db.stop)
        self.addCleanup(storage.stop)
        self.ref = self.db.reference.return_value
        self.bucket = self.storage.bucket.return_value

    def test_is_a_singleton(self):
        self.assertIs(FirebaseService(), firebase_service)

    def test_read_and_write(self):
        self.ref.get.return_value = {'name': 'Ana'}
        self.assertEqual(firebase_service.get_data('User/Trabajadores/a'), {'name': 'Ana'})
        self.db.reference.assert_called_with('User/Trabajadores/a')

        self.assertTrue(firebase_service.set_data('x', {'a': 1}))
        self.ref.set.assert_called_with({'a': 1})
        self.assertTrue(firebase_service.update_data('x', {'b': 2}))
        self.ref.update.assert_called_with({'b': 2})
        self.assertTrue(firebase_service.delete_data('x'))
        self.ref.delete.assert_called_once()

    def test_query_chains_only_the_given_filters(self):
        chained = self.ref.order_by_child.return_value.equal_to.return_value
        chained.limit_to_first.return_value.get.return_value = {'k': 1}

        result = firebase_service.query_data('requests', order_by='worker_id', equal_to='w1', limit_to_first=10)

        self.assertEqual(result, {'k': 1})
        self.ref.order_by_child.assert_called_with('worker_id')
        self.ref.order_by_child.return_value.equal_to.assert_called_with('w1')
        chained.limit_to_last.assert_not_called()

        self.ref.limit_to_last.return_value.get.return_value = {'z': 2}
        self.assertEqual(firebase_service.query_data('notifications/u', limit_to_last=50), {'z': 2})

    def test_storage(self):
        blob = self.bucket.blob.return_value
        blob.generate_signed_url.return_value = 'https://firmada'
        blob.public_url = 'https://publica'
        self.bucket.list_blobs.return_value = [mock.Mock(), mock.Mock()]
        self.bucket.list_blobs.return_value[0].name = 'worker_documents/u/a.pdf'
        self.bucket.list_blobs.return_value[1].name = 'worker_documents/u/b.pdf'

        self.assertEqual(firebase_service.get_file_url('worker_documents/u/a.pdf'), 'https://firmada')
        self.assertEqual(blob.generate_signed_url.call_args.kwargs['expiration'], 3600)
        self.assertEqual(firebase_service.upload_file_to_storage('/tmp/a.pdf', 'x/a.pdf'), 'https://publica')
        self.assertTrue(firebase_service.delete_file_from_storage('x/a.pdf'))
        self.assertEqual(firebase_service.list_files_in_folder('worker_documents/u/'),
                         ['worker_documents/u/a.pdf', 'worker_documents/u/b.pdf'])
        self.bucket.list_blobs.assert_called_with(prefix='worker_documents/u/')

    def test_errors_are_propagated(self):
        self.ref.get.side_effect = Exception('sin red')
        self.ref.set.side_effect = Exception('sin red')
        self.ref.update.side_effect = Exception('sin red')
        self.ref.delete.side_effect = Exception('sin red')
        self.ref.order_by_child.side_effect = Exception('sin red')
        self.storage.bucket.side_effect = Exception('sin bucket')
        calls = [
            lambda: firebase_service.get_data('x'), lambda: firebase_service.set_data('x', 1),
            lambda: firebase_service.update_data('x', {}), lambda: firebase_service.delete_data('x'),
            lambda: firebase_service.query_data('x', order_by='a'), lambda: firebase_service.get_file_url('x'),
            lambda: firebase_service.upload_file_to_storage('a', 'b'),
            lambda: firebase_service.delete_file_from_storage('x'), lambda: firebase_service.list_files_in_folder('x'),
        ]
        for call in calls:
            with self.subTest(call=call):
                with self.assertRaises(Exception):
                    call()

    def test_reference_error_is_propagated(self):
        self.db.reference.side_effect = ValueError('ruta inválida')
        with self.assertRaises(ValueError):
            firebase_service.get_database_reference('a.b')

    @mock.patch(f'{MODULE}.firebase_admin')
    @mock.patch(f'{MODULE}.credentials')
    def test_initializes_the_sdk_only_once(self, credentials, firebase_admin):
        firebase_admin._apps = {}
        firebase_service.initialize_firebase()
        firebase_admin.initialize_app.assert_called_once()
        options = firebase_admin.initialize_app.call_args.args[1]
        self.assertEqual(set(options), {'databaseURL', 'storageBucket'})

        firebase_admin._apps = {'[DEFAULT]': object()}
        firebase_service.initialize_firebase()
        firebase_admin.initialize_app.assert_called_once()

        firebase_admin._apps = {}
        credentials.Certificate.side_effect = FileNotFoundError('sin credencial')
        with self.assertRaises(FileNotFoundError):
            firebase_service.initialize_firebase()
