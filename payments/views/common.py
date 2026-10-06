from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from ..authentication import FirebaseIDTokenAuthentication

# Endpoints de la app: solo ID token de Firebase
APP_AUTHENTICATION = [FirebaseIDTokenAuthentication]

# Endpoints compartidos app/panel: Firebase primero (solo procesa tokens RS256),
# luego el JWT del panel
APP_OR_PANEL_AUTHENTICATION = [FirebaseIDTokenAuthentication, JWTAuthentication, SessionAuthentication]

INVALID_KEY_CHARS = set('/.#$[]')


def is_valid_firebase_key(value):
    return bool(value) and len(value) <= 255 and not (set(value) & INVALID_KEY_CHARS)


def error_response(message, status_code):
    return Response({'success': False, 'error': message}, status=status_code)


def invalid_id_response():
    return error_response('ID de solicitud inválido', status.HTTP_400_BAD_REQUEST)


def validation_error_response(errors):
    return Response({'success': False, 'errors': errors}, status=status.HTTP_400_BAD_REQUEST)
