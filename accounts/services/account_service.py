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
    SESSION_PATHS = ('Tokens/{uid}', 'active_workers/{uid}', 'WorkerDocuments/{uid}', 'notifications/{uid}')
    STORAGE_PREFIXES = ('worker_documents/{uid}/', 'client_images/{uid}/', 'worker_profiles/profile_{uid}_')

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

    def delete_account(self, uid):
        """
        Raises:
            ServiceRequestError: 409 si tiene un servicio en camino o en progreso
        """
        requests = self._requests_of(uid)
        if any(request.get('status') in self.ACTIVE_STATUSES for _, _, request in requests):
            raise ServiceRequestError(
                'Tienes un servicio en curso; termínalo antes de eliminar tu cuenta', 409)

        now = int(time.time() * 1000)
        for role, request_id, request in requests:
            _, contact_fields = self.ROLES[role]
            updates = dict(contact_fields, last_updated=now)
            cancelled = request.get('status') in self.CANCELLABLE_STATUSES
            if cancelled:
                updates.update(status='cancelled', cancelled_by=role, cancellation_reason_code='otro',
                               cancellation_reason_text='Cuenta eliminada', cancelled_at=now)
            self.firebase.update_data(f"requests/{request_id}", updates)
            if cancelled:
                # Se avisa a la otra parte, con el nombre ya anonimizado
                self.notifications.notify('request_cancelled', request_id, {**request, **updates})

        for template in self.PROFILE_PATHS + self.SESSION_PATHS:
            self.firebase.delete_data(template.format(uid=uid))

        for prefix in self.STORAGE_PREFIXES:
            for name in self.firebase.list_files_in_folder(prefix.format(uid=uid)):
                self.firebase.delete_file_from_storage(name)

        # Al final: si algo falla antes, el usuario puede reintentar con su sesión
        try:
            firebase_auth.delete_user(uid)
        except firebase_auth.UserNotFoundError:
            pass
        logger.info(f"Account {uid} deleted ({len(requests)} requests anonymized)")


account_service = AccountService()
