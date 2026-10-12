from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from ..permissions import IsAppUser
from ..serializers import (
    CancelSerializer,
    NotificationSerializer,
    QuoteRejectSerializer,
    QuoteSubmitSerializer,
    RatingSerializer,
    ScheduleSerializer,
    ServiceRequestCreateSerializer,
)
from ..services.notification_service import notification_service
from ..services.service_request_service import ServiceRequestError, service_request_service
from .common import (
    APP_AUTHENTICATION,
    error_response,
    invalid_id_response,
    is_valid_firebase_key,
    validation_error_response,
)
import logging

logger = logging.getLogger(__name__)


def _quote_data(request_id, request):
    return {
        'request_id': request_id,
        'status': request.get('status'),
        'quoted_price': request.get('quoted_price'),
        'quote_status': request.get('quote_status'),
    }


class AppServiceRequestView(APIView):
    """Base de los endpoints de la app sobre requests/<id>."""
    authentication_classes = APP_AUTHENTICATION
    permission_classes = [IsAppUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'service_requests'

    def run(self, request_id, action):
        if not is_valid_firebase_key(request_id):
            return invalid_id_response()
        try:
            return action()
        except ServiceRequestError as e:
            return error_response(e.message, e.status_code)
        except Exception as e:
            logger.error(f"Error on request {request_id}: {str(e)}")
            return error_response('No se pudo completar la operación', status.HTTP_500_INTERNAL_SERVER_ERROR)


class ServiceRequestCreateView(APIView):
    """
    POST /api/requests/   (cliente)
    Body: {"worker_id": "...", "service_category": "plomeria", "address": "...",
           "description": "...", "lat": 5.3086, "lng": -73.8150,
           "task_items": [{"task": "destapar-desague-sanitario", "quantity": 1}]}
    Crea la solicitud con el precio de referencia congelado y notifica al trabajador.
    """
    authentication_classes = APP_AUTHENTICATION
    permission_classes = [IsAppUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'service_requests'

    def post(self, request):
        serializer = ServiceRequestCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error_response(serializer.errors)

        try:
            created = service_request_service.create_request(request.user.uid, serializer.validated_data)
        except ServiceRequestError as e:
            return error_response(e.message, e.status_code)
        except Exception:
            logger.exception("Error creating service request")
            return error_response('No se pudo crear la solicitud', status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'success': True,
            'data': {
                'request_id': created['request_id'],
                'status': created['status'],
                'quote_reference': created['quote_reference'],
            }
        }, status=status.HTTP_201_CREATED)


class QuoteSubmitView(AppServiceRequestView):
    """
    POST /api/requests/<request_id>/quote/   (trabajador)
    Body: {"quoted_price": 85000, "adjustment_reason_code": "materiales",
           "adjustment_reason_text": "", "scheduled_at": 1792155600000,
           "estimated_duration_min": 90}
    El motivo es obligatorio si hay ítems sin rango o el precio sale del
    rango de referencia congelado; el texto, solo con «otro».
    """

    def post(self, request, request_id):
        serializer = QuoteSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error_response(serializer.errors)

        def action():
            updated = service_request_service.submit_quote(
                request.user.uid, request_id, serializer.validated_data)
            return Response({'success': True, 'data': _quote_data(request_id, updated)}, status=status.HTTP_200_OK)

        return self.run(request_id, action)


class ScheduleView(AppServiceRequestView):
    """
    POST /api/requests/<request_id>/schedule/   (trabajador)
    Body: {"scheduled_at": 1792159800000, "estimated_duration_min": 90}
    Reprograma una solicitud aceptada y avisa al cliente.
    """

    def post(self, request, request_id):
        serializer = ScheduleSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error_response(serializer.errors)

        def action():
            updated = service_request_service.reschedule(request.user.uid, request_id, serializer.validated_data)
            return Response({
                'success': True,
                'data': {
                    'request_id': request_id,
                    'scheduled_at': updated['scheduled_at'],
                    'estimated_duration_min': updated['estimated_duration_min'],
                    'reschedule_count': updated['reschedule_count'],
                }
            }, status=status.HTTP_200_OK)

        return self.run(request_id, action)


class CancelView(AppServiceRequestView):
    """
    POST /api/requests/<request_id>/cancel/   (cliente o trabajador)
    Body: {"reason_code": "horario", "reason_text": ""}
    Solo antes de «Iniciar viaje»; después responde 409 (PQR).
    """

    def post(self, request, request_id):
        serializer = CancelSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error_response(serializer.errors)

        def action():
            updated = service_request_service.cancel(
                request.user.uid, request_id,
                serializer.validated_data['reason_code'], serializer.validated_data['reason_text'])
            return Response({
                'success': True,
                'data': {
                    'request_id': request_id,
                    'status': updated['status'],
                    'cancelled_by': updated['cancelled_by'],
                }
            }, status=status.HTTP_200_OK)

        return self.run(request_id, action)


class QuoteAcceptView(AppServiceRequestView):
    """POST /api/requests/<request_id>/quote/accept/   (cliente)"""

    def post(self, request, request_id):
        def action():
            updated = service_request_service.accept_quote(request.user.uid, request_id)
            return Response({'success': True, 'data': _quote_data(request_id, updated)}, status=status.HTTP_200_OK)

        return self.run(request_id, action)


class QuoteRejectView(AppServiceRequestView):
    """
    POST /api/requests/<request_id>/quote/reject/   (cliente)
    Body: {"reason": "..."}  (opcional)
    """

    def post(self, request, request_id):
        serializer = QuoteRejectSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error_response(serializer.errors)

        def action():
            updated = service_request_service.reject_quote(
                request.user.uid, request_id, serializer.validated_data['reason'])
            return Response({'success': True, 'data': _quote_data(request_id, updated)}, status=status.HTTP_200_OK)

        return self.run(request_id, action)


class RatingView(AppServiceRequestView):
    """
    POST /api/requests/<request_id>/rating/   (cliente)
    Body: {"rating": 5, "comment": "..."}
    Requiere el servicio completado y pagado. El promedio del trabajador se
    recalcula en el servidor.
    """
    throttle_scope = 'ratings'

    def post(self, request, request_id):
        serializer = RatingSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error_response(serializer.errors)

        def action():
            updated = service_request_service.rate_service(
                request.user.uid, request_id,
                serializer.validated_data['rating'], serializer.validated_data['comment'])
            return Response({
                'success': True,
                'data': {
                    'request_id': request_id,
                    'is_rated': updated.get('is_rated'),
                    'client_rating': updated.get('client_rating'),
                }
            }, status=status.HTTP_200_OK)

        return self.run(request_id, action)


class QuoteLimitsView(APIView):
    """
    GET /api/requests/quote-limits/?service_type=Plomería
    Rango de precio permitido, para validar en la app antes de cotizar.
    """
    authentication_classes = APP_AUTHENTICATION
    permission_classes = [IsAppUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'service_requests'

    def get(self, request):
        limits = service_request_service.get_quote_limits(request.query_params.get('service_type'))
        return Response({'success': True, 'data': limits}, status=status.HTTP_200_OK)


class NotificationView(APIView):
    """
    POST /api/notifications/
    Body: {"request_id": "...", "type": "new_request|request_accepted|request_rejected|status_change"}

    Reemplaza el envío de FCM desde el teléfono. El servidor decide el
    destinatario y el texto a partir de la solicitud, y valida que quien
    notifica sea el participante correcto y que el estado corresponda.
    """
    authentication_classes = APP_AUTHENTICATION
    permission_classes = [IsAppUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'notifications'

    # tipo -> (rol que envía, estados válidos de la solicitud)
    RULES = {
        'new_request': ('client_id', ('pending',)),
        'request_accepted': ('worker_id', ('accepted',)),
        'request_rejected': ('worker_id', ('rejected',)),
        'status_change': ('worker_id', ('on_the_way', 'in_progress', 'completed')),
    }

    def post(self, request):
        serializer = NotificationSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error_response(serializer.errors)

        request_id = serializer.validated_data['request_id']
        notification_type = serializer.validated_data['type']
        sender_field, valid_statuses = self.RULES[notification_type]

        try:
            service_request = service_request_service.get_request(request_id)
        except ServiceRequestError as e:
            return error_response(e.message, e.status_code)

        if service_request.get(sender_field) != request.user.uid:
            return error_response('No participas en esta solicitud con ese rol', status.HTTP_403_FORBIDDEN)
        if service_request.get('status') not in valid_statuses:
            return error_response('El estado de la solicitud no corresponde a la notificación', status.HTTP_409_CONFLICT)

        sent = notification_service.notify(notification_type, request_id, service_request)
        return Response({'success': True, 'data': {'sent': sent}}, status=status.HTTP_200_OK)
