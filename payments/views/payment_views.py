from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from ..authentication import FirebaseUser
from ..models import Payment
from ..permissions import IsAppOrPanelUser, IsAppUser, IsPanelUser
from ..serializers import (
    PaymentAdminListSerializer,
    PaymentAdminSerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
)
from ..services.payment_service import payment_service
from ..services.service_request_service import ServiceRequestError
from .common import APP_OR_PANEL_AUTHENTICATION, error_response, validation_error_response
import logging

logger = logging.getLogger(__name__)


class PaymentListCreateView(APIView):
    """
    POST /api/payments/  (app, cliente)
        Inicia el pago de una solicitud completada con cotización aceptada.
        Body: {"service_request_id": "...", "redirect_url": "adsapp://..."}
        El monto lo calcula el servidor; cualquier monto enviado se ignora.

    GET  /api/payments/  (panel admin)
        Lista paginada. Filtros: ?status=APPROVED&service_request_id=...
    """
    authentication_classes = APP_OR_PANEL_AUTHENTICATION
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'payments'

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAppUser()]
        return [IsPanelUser()]

    def get(self, request):
        payments = Payment.objects.all()

        status_filter = request.query_params.get('status')
        if status_filter:
            payments = payments.filter(status=status_filter.upper())
        request_filter = request.query_params.get('service_request_id')
        if request_filter:
            payments = payments.filter(service_request_id=request_filter)

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(payments, request, view=self)
        serializer = PaymentAdminListSerializer(page, many=True)

        return Response({
            'success': True,
            'count': paginator.page.paginator.count,
            'next': paginator.get_next_link(),
            'previous': paginator.get_previous_link(),
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = PaymentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error_response(serializer.errors)

        try:
            payment, session, created = payment_service.start_payment(
                client_uid=request.user.uid,
                service_request_id=serializer.validated_data['service_request_id'],
                redirect_url=serializer.validated_data['redirect_url'],
            )
        except ServiceRequestError as e:
            return error_response(e.message, e.status_code)
        except Exception as e:
            logger.error(f"Error starting payment: {str(e)}")
            return error_response('No se pudo iniciar el pago', status.HTTP_500_INTERNAL_SERVER_ERROR)

        data = PaymentSerializer(payment).data
        data['checkout_url'] = session.checkout_url

        return Response({
            'success': True,
            'data': data
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class PaymentDetailView(APIView):
    """
    GET /api/payments/<reference>/
    Estado de un pago. Lo ven el cliente y el trabajador de la solicitud
    (app) o el panel admin (con historial de eventos).
    """
    authentication_classes = APP_OR_PANEL_AUTHENTICATION
    permission_classes = [IsAppOrPanelUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'payments'

    def get(self, request, reference):
        payment = Payment.objects.filter(reference=reference).first()

        if isinstance(request.user, FirebaseUser):
            # 404 también si no participa: no se revela que la referencia existe
            if payment is None or request.user.uid not in (payment.client_uid, payment.worker_uid):
                return error_response('Pago no encontrado', status.HTTP_404_NOT_FOUND)
            data = PaymentSerializer(payment).data
        else:
            if payment is None:
                return error_response('Pago no encontrado', status.HTTP_404_NOT_FOUND)
            data = PaymentAdminSerializer(payment).data

        return Response({
            'success': True,
            'data': data
        }, status=status.HTTP_200_OK)
