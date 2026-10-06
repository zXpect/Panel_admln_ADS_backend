import json
import logging
import time

from worker_verification.models import SystemConfig
from worker_verification.services.firebase_service import firebase_service

from .notification_service import notification_service

logger = logging.getLogger(__name__)


class ServiceRequestError(Exception):
    """Error de negocio sobre una solicitud; la vista lo traduce a HTTP."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _now_ms():
    return int(time.time() * 1000)


class ServiceRequestService:
    """
    Operaciones sobre requests/<id> que la app no puede hacer directamente
    (las reglas de Firebase las reservan al backend): cotización y calificación.

    Cada cambio se hace con una transacción de Firebase para que dos
    peticiones simultáneas no dejen la solicitud en un estado inconsistente.
    """

    REQUESTS_PATH = 'requests'
    WORKERS_PATH = 'User/Trabajadores'

    QUOTE_QUOTED = 'quoted'
    QUOTE_ACCEPTED = 'accepted'
    QUOTE_REJECTED = 'rejected'

    # Claves en SystemConfig (configurables desde el admin de Django)
    CONFIG_MIN_PRICE = 'quote_min_price_cop'
    CONFIG_MAX_PRICE = 'quote_max_price_cop'
    CONFIG_PRICE_RANGES = 'quote_price_ranges'   # JSON: {"Plomería": {"min": 20000, "max": 800000}}
    DEFAULT_MIN_PRICE = 1000
    DEFAULT_MAX_PRICE = 5000000

    MAX_REJECTION_REASON = 200
    MAX_RATING_COMMENT = 500

    def __init__(self):
        self.firebase = firebase_service
        self.notifications = notification_service

    # ---------- lectura ----------

    def get_request(self, request_id):
        request = self.firebase.get_data(f"{self.REQUESTS_PATH}/{request_id}")
        if not isinstance(request, dict):
            raise ServiceRequestError('Solicitud no encontrada', 404)
        return request

    # ---------- límites de precio ----------

    @staticmethod
    def _config_int(key, default):
        config = SystemConfig.objects.filter(key=key).first()
        try:
            return int(config.value) if config else default
        except (TypeError, ValueError):
            logger.error(f"Invalid SystemConfig value for {key}")
            return default

    def get_quote_limits(self, service_type=None):
        """
        Rango permitido (COP) para una cotización. Si el tipo de servicio tiene
        un rango propio en SystemConfig se usa; si no, el rango global.
        """
        min_price = self._config_int(self.CONFIG_MIN_PRICE, self.DEFAULT_MIN_PRICE)
        max_price = self._config_int(self.CONFIG_MAX_PRICE, self.DEFAULT_MAX_PRICE)

        ranges_config = SystemConfig.objects.filter(key=self.CONFIG_PRICE_RANGES).first()
        if ranges_config and service_type:
            try:
                ranges = json.loads(ranges_config.value)
                service_range = ranges.get(service_type) or {}
                min_price = int(service_range.get('min', min_price))
                max_price = int(service_range.get('max', max_price))
            except (TypeError, ValueError, AttributeError):
                logger.error(f"Invalid SystemConfig value for {self.CONFIG_PRICE_RANGES}")

        return {'min_price': min_price, 'max_price': max_price, 'currency': 'COP'}

    # ---------- transacciones ----------

    def _transact_request(self, request_id, update_fn):
        """
        Ejecuta update_fn(request) -> request dentro de una transacción.
        update_fn puede lanzar ServiceRequestError para abortar sin cambios.
        """
        ref = self.firebase.get_database_reference(f"{self.REQUESTS_PATH}/{request_id}")

        def transaction(current):
            if not isinstance(current, dict):
                raise ServiceRequestError('Solicitud no encontrada', 404)
            updated = dict(current)
            update_fn(updated)
            return updated

        return ref.transaction(transaction)

    # ---------- cotización ----------

    def submit_quote(self, worker_uid, request_id, quoted_price):
        """
        El trabajador cotiza (o vuelve a cotizar tras un rechazo). Si la
        solicitud estaba en 'pending', cotizar equivale a aceptarla.
        """
        def update(request):
            if request.get('worker_id') != worker_uid:
                raise ServiceRequestError('Solo el trabajador asignado puede cotizar', 403)
            if request.get('status') not in ('pending', 'accepted'):
                raise ServiceRequestError('La solicitud no admite cotizaciones en su estado actual', 409)
            if request.get('quote_status') == self.QUOTE_ACCEPTED:
                raise ServiceRequestError('La cotización ya fue aceptada y no se puede cambiar', 409)

            limits = self.get_quote_limits(request.get('service_type'))
            if not limits['min_price'] <= quoted_price <= limits['max_price']:
                raise ServiceRequestError(
                    f"El precio debe estar entre {limits['min_price']} y {limits['max_price']} COP", 400)

            now = _now_ms()
            if request.get('status') == 'pending':
                request['status'] = 'accepted'
            request['quoted_price'] = quoted_price
            request['quote_status'] = self.QUOTE_QUOTED
            request['quoted_at'] = now
            request['last_updated'] = now
            request.pop('quote_rejection_reason', None)

        request = self._transact_request(request_id, update)
        logger.info(f"Quote submitted for request {request_id}: {quoted_price} COP")
        self.notifications.notify('quote_received', request_id, request)
        return request

    def accept_quote(self, client_uid, request_id):
        def update(request):
            self._check_client_can_answer_quote(request, client_uid)
            now = _now_ms()
            request['quote_status'] = self.QUOTE_ACCEPTED
            request['quote_accepted_at'] = now
            request['last_updated'] = now

        request = self._transact_request(request_id, update)
        logger.info(f"Quote accepted for request {request_id}")
        self.notifications.notify('quote_accepted', request_id, request)
        return request

    def reject_quote(self, client_uid, request_id, reason=''):
        def update(request):
            self._check_client_can_answer_quote(request, client_uid)
            request['quote_status'] = self.QUOTE_REJECTED
            request['quote_rejection_reason'] = (reason or '')[:self.MAX_REJECTION_REASON]
            request['last_updated'] = _now_ms()

        request = self._transact_request(request_id, update)
        logger.info(f"Quote rejected for request {request_id}")
        self.notifications.notify('quote_rejected', request_id, request)
        return request

    def _check_client_can_answer_quote(self, request, client_uid):
        if request.get('client_id') != client_uid:
            raise ServiceRequestError('Solo el cliente de la solicitud puede responder la cotización', 403)
        if request.get('status') != 'accepted':
            raise ServiceRequestError('La solicitud no está esperando respuesta a una cotización', 409)
        if request.get('quote_status') != self.QUOTE_QUOTED:
            raise ServiceRequestError('No hay una cotización pendiente de respuesta', 409)

    # ---------- calificación ----------

    def rate_service(self, client_uid, request_id, rating, comment=''):
        """
        Registra la calificación del cliente y recalcula el promedio del
        trabajador en el servidor. Requiere el servicio completado y pagado.
        """
        def update(request):
            if request.get('client_id') != client_uid:
                raise ServiceRequestError('Solo el cliente de la solicitud puede calificar', 403)
            if request.get('status') != 'completed':
                raise ServiceRequestError('Solo se puede calificar un servicio completado', 409)
            if request.get('payment_status') != 'approved':
                raise ServiceRequestError('El servicio debe estar pagado antes de calificar', 409)
            if request.get('is_rated') is True:
                raise ServiceRequestError('Este servicio ya fue calificado', 409)

            now = _now_ms()
            request['is_rated'] = True
            request['client_rating'] = rating
            request['client_comment'] = (comment or '')[:self.MAX_RATING_COMMENT]
            request['rated_at'] = now
            request['last_updated'] = now

        request = self._transact_request(request_id, update)
        self._add_worker_rating(request['worker_id'], rating)
        logger.info(f"Request {request_id} rated with {rating}")
        return request

    def _add_worker_rating(self, worker_id, rating):
        """Misma fórmula que WorkerService.update_worker_rating, pero transaccional."""
        ref = self.firebase.get_database_reference(f"{self.WORKERS_PATH}/{worker_id}")

        def transaction(worker):
            if not isinstance(worker, dict):
                raise ServiceRequestError('Trabajador no encontrado', 404)
            total = int(worker.get('totalRatings') or 0)
            current = float(worker.get('rating') or 0)
            worker = dict(worker)
            worker['rating'] = round((current * total + rating) / (total + 1), 2)
            worker['totalRatings'] = total + 1
            worker['timestamp'] = _now_ms()
            return worker

        try:
            ref.transaction(transaction)
        except Exception as e:
            # La calificación ya quedó en la solicitud; el promedio se puede recalcular
            logger.error(f"Error updating rating of worker {worker_id}: {str(e)}")
            raise


service_request_service = ServiceRequestService()
