"""Dobles de prueba: Firebase Realtime Database en memoria y tokens de la app."""
import base64
import copy
import json
from unittest import mock

from firebase_admin import auth as firebase_auth


class FakeReference:
    def __init__(self, firebase, path):
        self.firebase = firebase
        self.path = path

    @property
    def key(self):
        return self.path.rstrip('/').split('/')[-1]

    def push(self):
        # Claves crecientes como las de Firebase ('-N0001', '-N0002'...)
        self.firebase.push_count += 1
        return FakeReference(self.firebase, f"{self.path}/-N{self.firebase.push_count:04d}")

    def set(self, value):
        self.firebase.set_data(self.path, value)

    def transaction(self, update_fn):
        # Como el SDK admin: las excepciones de update_fn abortan sin escribir
        new_value = update_fn(copy.deepcopy(self.firebase.get_data(self.path)))
        self.firebase.set_data(self.path, new_value)
        return new_value


class FakeFirebase:
    """Subconjunto de FirebaseService usado por payments, sobre un dict."""

    def __init__(self, data=None):
        self.data = copy.deepcopy(data or {})
        self.push_count = 0

    @staticmethod
    def _keys(path):
        return [key for key in path.split('/') if key]

    def get_data(self, path):
        node = self.data
        for key in self._keys(path):
            if not isinstance(node, dict) or key not in node:
                return None
            node = node[key]
        return copy.deepcopy(node)

    def set_data(self, path, value):
        keys = self._keys(path)
        node = self.data
        for key in keys[:-1]:
            node = node.setdefault(key, {})
        if value is None:
            node.pop(keys[-1], None)
        else:
            node[keys[-1]] = copy.deepcopy(value)
        return True

    def update_data(self, path, values):
        for key, value in values.items():
            self.set_data(f"{path}/{key}", value)
        return True

    def delete_data(self, path):
        return self.set_data(path, None)

    def get_database_reference(self, path=''):
        return FakeReference(self, path)


def _b64(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')


def app_token(uid):
    """Token con la forma de un ID token de Firebase (RS256); la firma no se verifica en pruebas."""
    signature = base64.urlsafe_b64encode(b'firma-de-prueba').decode().rstrip('=')
    return f"{_b64({'alg': 'RS256', 'kid': 'test'})}.{_b64({'uid': uid})}.{signature}"


def _decode_uid(token, check_revoked=False):
    payload = token.split('.')[1]
    payload += '=' * (-len(payload) % 4)
    data = json.loads(base64.urlsafe_b64decode(payload))
    if data['uid'] == 'revoked':
        raise firebase_auth.RevokedIdTokenError('revoked')
    if data['uid'] == 'invalid':
        raise firebase_auth.InvalidIdTokenError('invalid')
    return {'uid': data['uid']}


def patch_verify_id_token():
    return mock.patch('payments.authentication.firebase_auth.verify_id_token', side_effect=_decode_uid)
