import logging
import time

from pricing.models import ServiceCategory
from pricing.services import pricing_service
from pricing.services.pricing_service import json_number
from pricing.services.worker_categories import worker_categories
from worker_verification.services.firebase_service import firebase_service

from ..serializers.service_request_serializers import CANCELLATION_REASONS, OTHER_REASON
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


def _drop_none(request):
    """Firebase no guarda nulos: un campo en None se elimina de la solicitud."""
    for key in [key for key, value in request.items() if value is None]:
        del request[key]


class ServiceRequestService:
    """
    Operaciones sobre requests/<id> que la app no puede hacer directamente
    (las reglas de Firebase las reservan al backend): creación, cotización y calificación.

    Cada cambio se hace con una transacción de Firebase para que dos
    peticiones simultáneas no dejen la solicitud en un estado inconsistente.
    """

    REQUESTS_PATH = 'requests'
    WORKERS_PATH = 'User/Trabajadores'
    CLIENTS_PATH = 'User/Clientes'

    QUOTE_QUOTED = 'quoted'
    QUOTE_ACCEPTED = 'accepted'
    QUOTE_REJECTED = 'rejected'

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

    def get_quote_limits(self, service_type=None):
        """
        Rango permitido (COP) para una cotización: de la tarifa mínima por
        visita al tope técnico (D4, D6). `service_type` se ignora; se conserva
        la firma por la app anterior (GET /api/requests/quote-limits/).
        """
        return {
            'min_price': pricing_service.min_visit_fee_cop(),
            'max_price': pricing_service.max_price_cop(),
            'currency': 'COP',
        }

    # ---------- creación ----------

    def create_request(self, client_uid, data):
        """
        Crea requests/<id> (B18, B14). Valida al trabajador (verificado y con el
        oficio pedido), congela el precio de referencia, escribe en Firebase y
        notifica al trabajador. `data` es el validated_data de
        ServiceRequestCreateSerializer.
        """
        category = data['category']
        worker_id = data['worker_id']
        if worker_id == client_uid:
            raise ServiceRequestError('No puedes solicitarte un servicio a ti mismo', 400)

        client = self.firebase.get_data(f"{self.CLIENTS_PATH}/{client_uid}")
        if not isinstance(client, dict):
            raise ServiceRequestError('Solo un cliente registrado puede crear solicitudes', 403)

        worker = self.firebase.get_data(f"{self.WORKERS_PATH}/{worker_id}")
        if not isinstance(worker, dict):
            raise ServiceRequestError('Trabajador no encontrado', 404)
        if (worker.get('verificationStatus') or {}).get('status') != 'approved' or worker.get('isActive') is False:
            raise ServiceRequestError('El trabajador no tiene la verificación aprobada', 409)
        valid_slugs = set(ServiceCategory.objects.filter(is_active=True).values_list('slug', flat=True))
        if category.slug not in worker_categories(worker, valid_slugs):
            raise ServiceRequestError('El trabajador no ejerce el oficio pedido', 409)

        quote_reference = pricing_service.estimate(data['items'])
        task_items = [
            {'task': item['task'].slug, 'quantity': json_number(item['quantity'])} if item['task']
            else {'custom_description': item['custom_description'], 'quantity': json_number(item['quantity'])}
            for item in data['items']
        ]

        now = _now_ms()
        ref = self.firebase.get_database_reference(self.REQUESTS_PATH).push()
        request_id = ref.key
        request = {
            'id': request_id,
            'request_id': request_id,
            'client_id': client_uid,
            'client_name': client.get('name') or 'Cliente',
            'client_phone': client.get('phone') or '',
            'client_email': client.get('email') or '',
            'worker_id': worker_id,
            'worker_name': worker.get('name') or 'Trabajador',
            'worker_phone': worker.get('phone') or '',
            'service_category': category.slug,
            'service_type': category.name,
            'address': data['address'],
            'description': data.get('description', ''),
            'lat': data['lat'],
            'lng': data['lng'],
            'task_items': task_items,
            'quote_reference': quote_reference,
            'status': 'pending',
            'is_rated': False,
            'timestamp': now,
            'last_updated': now,
        }
        for field in ('search_started_at', 'worker_selected_at'):
            if field in data:
                request[field] = data[field]

        ref.set(request)
        logger.info(f"Request {request_id} created by client {client_uid} for worker {worker_id}")
        self.notifications.notify('new_request', request_id, request)
        return request

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

    def submit_quote(self, worker_uid, request_id, quote):
        """
        El trabajador cotiza y agenda (o vuelve a cotizar tras un rechazo). Si
        la solicitud estaba en 'pending', cotizar equivale a aceptarla.
        `quote` es el validated_data de QuoteSubmitSerializer.
        """
        quoted_price = quote['quoted_price']
        reason_code = quote['adjustment_reason_code']

        def update(request):
            if request.get('worker_id') != worker_uid:
                raise ServiceRequestError('Solo el trabajador asignado puede cotizar', 403)
            if request.get('status') not in ('pending', 'accepted'):
                raise ServiceRequestError('La solicitud no admite cotizaciones en su estado actual', 409)
            if request.get('quote_status') == self.QUOTE_ACCEPTED:
                raise ServiceRequestError('La cotización ya fue aceptada y no se puede cambiar', 409)

            limits = self.get_quote_limits()
            if quoted_price < limits['min_price']:
                raise ServiceRequestError(
                    f"El precio debe ser de al menos {limits['min_price']} COP (tarifa mínima por visita)", 400)
            if quoted_price > limits['max_price']:
                raise ServiceRequestError('El precio supera el máximo permitido', 400)

            adjusted = self.is_adjusted_price(request.get('quote_reference'), quoted_price)
            if adjusted and not reason_code:
                raise ServiceRequestError(
                    'Indica el motivo del ajuste: el precio está fuera del rango de referencia '
                    'o hay ítems sin rango', 400)

            now = _now_ms()
            if request.get('status') == 'pending':
                request['status'] = 'accepted'
            request['quoted_price'] = quoted_price
            request['quote_status'] = self.QUOTE_QUOTED
            request['quoted_at'] = now
            request['quote_is_adjusted'] = adjusted
            # Sin ajuste no se guarda motivo; el texto solo acompaña a «otro» (D5)
            request['quote_adjustment_reason_code'] = reason_code if adjusted else None
            request['quote_adjustment_reason_text'] = (
                quote['adjustment_reason_text'] if adjusted and reason_code == OTHER_REASON else None)
            request['scheduled_at'] = quote['scheduled_at']
            request['estimated_duration_min'] = quote['estimated_duration_min']
            request['last_updated'] = now
            request.pop('quote_rejection_reason', None)
            _drop_none(request)

        request = self._transact_request(request_id, update)
        logger.info(f"Quote submitted for request {request_id}: {quoted_price} COP")
        self.notifications.notify('quote_received', request_id, request)
        return request

    @staticmethod
    def is_adjusted_price(quote_reference, quoted_price):
        """
        Verdadero si hay ítems sin rango o el precio queda fuera de [min_cop, max_cop].
        Una solicitud anterior al catálogo (sin quote_reference) cuenta como todo sin rango.
        """
        if not isinstance(quote_reference, dict) or quote_reference.get('has_unpriced_items', True):
            return True
        min_cop, max_cop = quote_reference.get('min_cop'), quote_reference.get('max_cop')
        if min_cop is None or max_cop is None:
            return True
        return not min_cop <= quoted_price <= max_cop

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

    # ---------- agenda ----------

    def reschedule(self, worker_uid, request_id, schedule):
        """El trabajador cambia la fecha, la hora o la duración (D9); se avisa al cliente."""
        def update(request):
            if request.get('worker_id') != worker_uid:
                raise ServiceRequestError('Solo el trabajador asignado puede reprogramar', 403)
            if request.get('status') != 'accepted':
                raise ServiceRequestError('Solo se puede reprogramar una solicitud aceptada que no ha iniciado', 409)

            now = _now_ms()
            request['scheduled_at'] = schedule['scheduled_at']
            request['estimated_duration_min'] = schedule['estimated_duration_min']
            request['rescheduled_at'] = now
            request['reschedule_count'] = int(request.get('reschedule_count') or 0) + 1
            request['last_updated'] = now

        request = self._transact_request(request_id, update)
        logger.info(f"Request {request_id} rescheduled ({request['reschedule_count']})")
        self.notifications.notify('request_rescheduled', request_id, request)
        return request

    # ---------- cancelación ----------

    CANCELLABLE_STATUSES = ('pending', 'accepted')
    STARTED_STATUSES = ('on_the_way', 'in_progress', 'completed')

    def cancel(self, uid, request_id, reason_code, reason_text=''):
        """
        Cliente o trabajador cancelan sin cobro antes de «Iniciar viaje» (D8).
        Desde on_the_way el caso se tramita como PQR.
        """
        def update(request):
            if uid == request.get('client_id'):
                role = 'client'
            elif uid == request.get('worker_id'):
                role = 'worker'
            else:
                raise ServiceRequestError('No participas en esta solicitud', 403)

            status = request.get('status')
            if status in self.STARTED_STATUSES:
                raise ServiceRequestError(
                    'El servicio ya inició y no se puede cancelar; tramítalo como PQR', 409)
            if status not in self.CANCELLABLE_STATUSES:
                raise ServiceRequestError('La solicitud ya está cerrada', 409)
            if reason_code not in CANCELLATION_REASONS[role]:
                raise ServiceRequestError('Motivo de cancelación no válido para tu rol', 400)

            now = _now_ms()
            request['status'] = 'cancelled'
            request['cancelled_by'] = role
            request['cancellation_reason_code'] = reason_code
            request['cancellation_reason_text'] = reason_text if reason_code == OTHER_REASON else None
            request['cancelled_at'] = now
            request['last_updated'] = now
            _drop_none(request)

        request = self._transact_request(request_id, update)
        logger.info(f"Request {request_id} cancelled by {request['cancelled_by']}")
        self.notifications.notify('request_cancelled', request_id, request)
        return request

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
