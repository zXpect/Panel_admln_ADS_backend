import hashlib
import logging
import time

from firebase_admin import auth as firebase_auth

from payments.services.notification_service import notification_service
from payments.services.service_request_service import ServiceRequestError
from worker_verification.services.firebase_service import firebase_service

logger = logging.getLogger(__name__)

DELETED_NAME = 'Usuario eliminado'


class AccountService:
    """
    Supresión de la cuenta por el propio usuario (Ley 1581, D18). Borra el
    perfil, los datos de sesión y los archivos, cancela las solicitudes que no
    han iniciado y anonimiza los datos de contacto de las anteriores, que la
    otra parte conserva. Los Payment y las PQR guardan solo el uid.

    También suspende y reactiva cuentas desde el panel (RF-21, HU-32): una
    cuenta suspendida no puede iniciar sesión.
    """

    # Con el servicio en curso no se elimina la cuenta: la otra parte depende de él
    ACTIVE_STATUSES = ('on_the_way', 'in_progress')
    # Las que no han iniciado se cancelan para que no queden esperando
    CANCELLABLE_STATUSES = ('pending', 'accepted')

    # Rol -> (campo del uid en la solicitud, campos de contacto a anonimizar)
    ROLES = {
        'client': ('client_id', {'client_name': DELETED_NAME, 'client_phone': '', 'client_email': ''}),
        'worker': ('worker_id', {'worker_name': DELETED_NAME, 'worker_phone': ''}),
    }

    PROFILE_PATHS = ('User/Clientes/{uid}', 'User/Trabajadores/{uid}')
    PROFILE_ROLES = (('client', 'User/Clientes/{uid}'), ('worker', 'User/Trabajadores/{uid}'))
    SUSPENDED_REASON = 'Cuenta suspendida'
    SESSION_PATHS = ('Tokens/{uid}', 'active_workers/{uid}', 'WorkerDocuments/{uid}', 'notifications/{uid}')
    STORAGE_PREFIXES = ('worker_documents/{uid}/', 'client_images/{uid}/', 'worker_profiles/profile_{uid}_')
    # Cuentas eliminadas, por el hash del correo: el login de la app explica que la
    # cuenta ya no existe en vez de «contraseña incorrecta». Solo lo lee el backend.
    DELETED_PATH = 'deleted_accounts'
    DELETED_BY_USER = 'user'
    DELETED_BY_ADMIN = 'admin'

    def __init__(self):
        self.firebase = firebase_service
        self.notifications = notification_service

    def _requests_of(self, uid):
        """[(rol, request_id, solicitud)] de las solicitudes del usuario como cliente o trabajador."""
        found = []
        for role, (field, _) in self.ROLES.items():
            results = self.firebase.query_data('requests', order_by=field, equal_to=uid) or {}
            found += [(role, request_id, request) for request_id, request in results.items()
                      if isinstance(request, dict)]
        return found

    def _has_active_service(self, requests):
        return any(request.get('status') in self.ACTIVE_STATUSES for _, _, request in requests)

    def _close_requests(self, requests, reason_text, anonymize):
        """
        Cancela las solicitudes que no han iniciado, con aviso a la otra parte, y
        con anonymize borra los datos de contacto del usuario en todas.
        """
        now = int(time.time() * 1000)
        for role, request_id, request in requests:
            cancelled = request.get('status') in self.CANCELLABLE_STATUSES
            if not (cancelled or anonymize):
                continue
            updates = {'last_updated': now}
            if anonymize:
                updates.update(self.ROLES[role][1])
            if cancelled:
                updates.update(status='cancelled', cancelled_by=role, cancellation_reason_code='otro',
                               cancellation_reason_text=reason_text, cancelled_at=now)
            self.firebase.update_data(f"requests/{request_id}", updates)
            if cancelled:
                # Se avisa a la otra parte (con el nombre ya anonimizado si aplica)
                self.notifications.notify('request_cancelled', request_id, {**request, **updates})

    def find_profile(self, uid):
        """(rol, ruta, perfil) del usuario en User/Clientes o User/Trabajadores, o (None, None, None)."""
        for role, template in self.PROFILE_ROLES:
            path = template.format(uid=uid)
            profile = self.firebase.get_data(path)
            if isinstance(profile, dict):
                return role, path, profile
        return None, None, None

    def set_active(self, uid, active):
        """
        Suspende (active=False) o reactiva una cuenta. Al suspender: deshabilita
        el usuario en Firebase Auth (no puede iniciar sesión), revoca sus
        sesiones (la API las rechaza con check_revoked), marca isActive=false, saca
        al trabajador de la búsqueda y cancela sus solicitudes que no han iniciado.
        Al reactivar solo habilita la cuenta; el trabajador vuelve a conectarse él mismo.

        Returns:
            tuple: (rol, estaba_activa)

        Raises:
            ServiceRequestError: 404 si no existe; 409 si tiene un servicio en camino o en progreso
        """
        role, path, profile = self.find_profile(uid)
        if role is None:
            raise ServiceRequestError('Cuenta no encontrada', 404)
        was_active = profile.get('isActive') is not False

        requests = []
        if not active:
            requests = self._requests_of(uid)
            if self._has_active_service(requests):
                raise ServiceRequestError(
                    'La cuenta tiene un servicio en camino o en progreso; suspéndela cuando termine', 409)

        # Primero Firebase Auth, para que no pueda actuar mientras se cierra lo demás.
        # Si algo falla después, repetir la petición completa el cambio.
        try:
            firebase_auth.update_user(uid, disabled=not active)
            if not active:
                firebase_auth.revoke_refresh_tokens(uid)
        except firebase_auth.UserNotFoundError:
            logger.warning(f"Account {uid} has a profile but no Firebase Auth user")

        updates = {'isActive': active}
        if role == 'worker' and not active:
            updates.update(isAvailable=False, isOnline=False)
            self.firebase.delete_data(f"active_workers/{uid}")
        self.firebase.update_data(path, updates)

        if not active:
            self._close_requests(requests, self.SUSPENDED_REASON, anonymize=False)
        logger.info(f"Account {uid} ({role}) {'reactivated' if active else 'suspended'}")
        return role, was_active

    def delete_account(self, uid, deleted_by=DELETED_BY_USER):
        """
        deleted_by: 'user' (Eliminar mi cuenta en la app) o 'admin' (panel, DEF-34).

        Raises:
            ServiceRequestError: 409 si tiene un servicio en camino o en progreso
        """
        requests = self._requests_of(uid)
        if self._has_active_service(requests):
            raise ServiceRequestError(
                'Tienes un servicio en curso; termínalo antes de eliminar tu cuenta', 409)

        self._close_requests(requests, 'Cuenta eliminada', anonymize=True)
        email = self._email_of(uid)

        for template in self.PROFILE_PATHS + self.SESSION_PATHS:
            self.firebase.delete_data(template.format(uid=uid))

        for prefix in self.STORAGE_PREFIXES:
            for name in self.firebase.list_files_in_folder(prefix.format(uid=uid)):
                self.firebase.delete_file_from_storage(name)

        if email:
            self.firebase.set_data(f"{self.DELETED_PATH}/{email_key(email)}",
                                   {'deleted_by': deleted_by, 'deleted_at': int(time.time() * 1000)})

        # Al final: si algo falla antes, el usuario puede reintentar con su sesión
        try:
            firebase_auth.delete_user(uid)
        except firebase_auth.UserNotFoundError:
            pass
        logger.info(f"Account {uid} deleted by {deleted_by} ({len(requests)} requests anonymized)")

    def _email_of(self, uid):
        """Correo de la cuenta en Firebase Auth o, si no se puede leer, el del perfil."""
        try:
            email = firebase_auth.get_user(uid).email
            if email:
                return email
        except Exception:
            pass
        _, _, profile = self.find_profile(uid)
        return (profile or {}).get('email')

    def deletion_of(self, email):
        """
        'user' o 'admin' si la cuenta de ese correo fue eliminada, o None. Si el
        correo volvió a registrarse, el registro ya no aplica y se borra.
        """
        path = f"{self.DELETED_PATH}/{email_key(email)}"
        record = self.firebase.get_data(path)
        if not isinstance(record, dict):
            return None
        try:
            firebase_auth.get_user_by_email(email.strip().lower())
            self.firebase.delete_data(path)
            return None
        except firebase_auth.UserNotFoundError:
            return record.get('deleted_by') or self.DELETED_BY_USER


def email_key(email):
    """Clave del correo en deleted_accounts: SHA-256 del correo en minúsculas, sin guardarlo."""
    return hashlib.sha256(email.strip().lower().encode('utf-8')).hexdigest()


account_service = AccountService()
