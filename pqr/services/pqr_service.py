import logging

from django.db import transaction
from django.utils import timezone

from payments.services.notification_service import notification_service
from payments.services.service_request_service import ServiceRequestError, service_request_service

from ..models import PQR
from .business_days import add_business_days

logger = logging.getLogger(__name__)


class PqrService:
    """
    PQR de la app y su atención desde el panel (B11, D21). El plazo de
    respuesta es único: 15 días hábiles desde el registro.
    """

    RESPONSE_BUSINESS_DAYS = 15

    def __init__(self):
        self.requests = service_request_service
        self.notifications = notification_service

    def create(self, uid, data):
        """
        Registra la PQR del cliente o del trabajador de la solicitud. El rol
        sale de la solicitud, no de la app.

        Raises:
            ServiceRequestError: la solicitud no existe (404) o no participa (403)
        """
        request = self.requests.get_request(data['service_request_id'])
        if uid == request.get('client_id'):
            role = PQR.ROLE_CLIENT
        elif uid == request.get('worker_id'):
            role = PQR.ROLE_WORKER
        else:
            raise ServiceRequestError('No participas en esta solicitud', 403)

        now = timezone.now()
        pqr = PQR.objects.create(
            service_request_id=data['service_request_id'],
            author_uid=uid,
            author_role=role,
            type=data['type'],
            description=data['description'],
            due_at=add_business_days(now, self.RESPONSE_BUSINESS_DAYS),
        )
        logger.info(f"PQR {pqr.id} ({pqr.type}) created by {role} on request {pqr.service_request_id}")
        return pqr

    def answer(self, admin, pqr_id, data):
        """
        El panel cambia el estado y responde. Cerrar exige respuesta; una PQR
        cerrada ya no cambia. Si llega una respuesta nueva se avisa al autor.

        Raises:
            ServiceRequestError: no existe (404), ya está cerrada (409) o falta la respuesta (400)
        """
        with transaction.atomic():
            pqr = PQR.objects.select_for_update().filter(pk=pqr_id).first()
            if pqr is None:
                raise ServiceRequestError('PQR no encontrada', 404)
            if pqr.status == PQR.STATUS_CLOSED:
                raise ServiceRequestError('La PQR ya está cerrada', 409)

            response = (data.get('response') or '').strip()
            new_response = bool(response) and response != (pqr.response or '')
            if data['status'] == PQR.STATUS_CLOSED and not (response or pqr.response):
                raise ServiceRequestError('Para cerrar la PQR escribe la respuesta al usuario', 400)

            pqr.status = data['status']
            if new_response:
                pqr.response = response
                pqr.responded_by = admin
            if pqr.status == PQR.STATUS_CLOSED:
                pqr.closed_at = timezone.now()
            pqr.save()

        logger.info(f"PQR {pqr.id} -> {pqr.status} by {admin.username}")
        if new_response:
            self.notifications.notify_pqr_answered(pqr)
        return pqr


pqr_service = PqrService()
