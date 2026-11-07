"""
Rol de evaluador del panel (jurados del trabajo de grado).

Un evaluador es una cuenta del panel (auth.User) en el grupo «evaluadores». Puede ver todo el
panel y hacer las acciones de revisión, pero no las que borran o cambian la configuración:

- Permitido: aprobar o rechazar documentos, cambiar el estado de verificación de un trabajador,
  responder PQR y suspender o reactivar cuentas (todas reversibles y con bitácora).
- Bloqueado: eliminar trabajadores o documentos, crear o editar trabajadores, carga masiva,
  catálogo, tarifas y configuración del sistema.

El control vive en un middleware (no en cada vista) para que ninguna vista con permisos propios
se lo salte: se evalúa con lista de permitidos, así que un endpoint nuevo queda bloqueado para
los evaluadores hasta que se agregue aquí a propósito.
"""
from datetime import date

from django.conf import settings
from django.http import JsonResponse
from django.urls import Resolver404, resolve
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

EVALUATOR_GROUP = 'evaluadores'

SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')

# (método, nombre de la ruta) que un evaluador puede ejecutar además de las lecturas
EVALUATOR_ALLOWED = {
    ('POST', 'document-approve-document'),
    ('POST', 'document-reject-document'),
    ('PATCH', 'worker-update-verification-status'),
    ('PATCH', 'pqr:pqr-detail'),
    ('PATCH', 'accounts:admin-account-status'),
    # El login y la renovación del token no llevan sesión, pero por si el panel manda el encabezado
    ('POST', 'token_obtain_pair'),
    ('POST', 'token_refresh'),
}

FORBIDDEN_MESSAGE = 'Cuenta de evaluación: esta acción no está permitida.'
EXPIRED_MESSAGE = 'El periodo de evaluación terminó; esta cuenta ya no tiene acceso.'


def is_evaluator(user):
    return bool(user and getattr(user, 'is_authenticated', False)
                and hasattr(user, 'groups') and user.groups.filter(name=EVALUATOR_GROUP).exists())


def access_until():
    """Último día de acceso de los evaluadores (settings.EVALUATOR_ACCESS_UNTIL, AAAA-MM-DD)."""
    return date.fromisoformat(settings.EVALUATOR_ACCESS_UNTIL)


def access_expired(today=None):
    return (today or date.today()) > access_until()


class PanelTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login del panel: agrega el nombre y el rol al token y cierra el acceso de evaluación vencido."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.get_username()
        # Nombre que muestra el encabezado del panel: el nombre completo si la cuenta lo tiene
        token['name'] = user.get_full_name() or user.get_username()
        token['role'] = 'evaluador' if is_evaluator(user) else 'admin'
        if is_evaluator(user):
            token['access_until'] = settings.EVALUATOR_ACCESS_UNTIL
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        if is_evaluator(self.user) and access_expired():
            from rest_framework.exceptions import AuthenticationFailed
            raise AuthenticationFailed(EXPIRED_MESSAGE, code='evaluation_expired')
        return data


class EvaluatorGuardMiddleware:
    """Bloquea para los evaluadores todo lo que no sea lectura o una acción de EVALUATOR_ALLOWED."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.jwt = JWTAuthentication()

    def __call__(self, request):
        if request.path.startswith('/api/'):
            user = self._panel_user(request)
            if is_evaluator(user):
                blocked = self._check(request)
                if blocked:
                    return blocked
        return self.get_response(request)

    def _panel_user(self, request):
        # Mismo orden que DRF: primero el JWT del panel; si no, la sesión de Django.
        # Un token inválido o de la app (Firebase) no es de un evaluador: la vista decide.
        try:
            result = self.jwt.authenticate(request)
        except (InvalidToken, TokenError):
            return None
        if result:
            return result[0]
        user = getattr(request, 'user', None)
        return user if user is not None and user.is_authenticated else None

    def _check(self, request):
        if access_expired():
            return JsonResponse({'success': False, 'error': EXPIRED_MESSAGE}, status=403)
        if request.method in SAFE_METHODS:
            return None
        try:
            view_name = resolve(request.path_info).view_name
        except Resolver404:
            return None
        if (request.method, view_name) in EVALUATOR_ALLOWED:
            return None
        return JsonResponse({'success': False, 'error': FORBIDDEN_MESSAGE, 'code': 'evaluator_forbidden'},
                            status=403)
