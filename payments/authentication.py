import logging

import jwt
from firebase_admin import auth as firebase_auth
from rest_framework import authentication, exceptions

from worker_verification.services.firebase_service import firebase_service  # noqa: F401  (inicializa el SDK)

logger = logging.getLogger(__name__)


class FirebaseUser:
    """
    Usuario de la app móvil autenticado con un ID token de Firebase.
    No existe en la tabla auth.User: solo se expone el uid.
    """
    is_authenticated = True
    is_anonymous = False
    is_staff = False
    is_superuser = False

    def __init__(self, uid, claims=None):
        self.uid = uid
        self.claims = claims or {}

    @property
    def pk(self):
        # Lo usan los throttles de DRF para identificar al usuario
        return self.uid

    @property
    def id(self):
        return self.uid

    def __str__(self):
        return f"firebase:{self.uid}"


class FirebaseIDTokenAuthentication(authentication.BaseAuthentication):
    """
    Autentica a la app móvil con el ID token de Firebase Auth:
        Authorization: Bearer <idToken>

    El panel admin usa el mismo header con un JWT HS256 de simplejwt. Los ID
    tokens de Firebase son RS256, así que esta clase solo procesa tokens RS256
    y deja pasar los demás (return None) a JWTAuthentication.
    """
    keyword = 'Bearer'

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header or header[0].decode().lower() != self.keyword.lower():
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed('Header Authorization inválido')

        token = header[1].decode()
        try:
            algorithm = jwt.get_unverified_header(token).get('alg')
        except jwt.exceptions.DecodeError:
            return None
        if algorithm != 'RS256':
            return None

        try:
            # check_revoked: una sesión cerrada o una cuenta deshabilitada deja de funcionar
            claims = firebase_auth.verify_id_token(token, check_revoked=True)
        except firebase_auth.RevokedIdTokenError:
            raise exceptions.AuthenticationFailed('Sesión revocada')
        except firebase_auth.UserDisabledError:
            raise exceptions.AuthenticationFailed('Cuenta deshabilitada')
        except (firebase_auth.ExpiredIdTokenError, firebase_auth.InvalidIdTokenError):
            raise exceptions.AuthenticationFailed('Token inválido o expirado')
        except Exception as e:
            logger.error(f"Error verifying Firebase ID token: {str(e)}")
            raise exceptions.AuthenticationFailed('No se pudo verificar el token')

        return FirebaseUser(claims['uid'], claims), token

    def authenticate_header(self, request):
        return self.keyword
