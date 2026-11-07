from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase

from ..services import auth_dates


def user(uid, created):
    return SimpleNamespace(uid=uid, user_metadata=SimpleNamespace(creation_timestamp=created))


class AuthDatesTests(SimpleTestCase):

    def setUp(self):
        cache.delete(auth_dates.CACHE_KEY)
        self.addCleanup(cache.delete, auth_dates.CACHE_KEY)

    @mock.patch.object(auth_dates.firebase_auth, 'list_users')
    def test_reads_auth_once_and_caches(self, list_users):
        list_users.return_value.iterate_all.return_value = [user('a', 10), user('b', 20)]
        accounts = auth_dates.attach_created_at([{'id': 'b'}, {'id': 'sin-auth'}])
        self.assertEqual([a['createdAt'] for a in accounts], [20, None])
        auth_dates.creation_times()
        list_users.assert_called_once()

    @mock.patch.object(auth_dates.firebase_auth, 'list_users', side_effect=Exception('caído'))
    def test_auth_error_leaves_dates_empty(self, _):
        self.assertEqual(auth_dates.attach_created_at([{'id': 'a'}]), [{'id': 'a', 'createdAt': None}])
