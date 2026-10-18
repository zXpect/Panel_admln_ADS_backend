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
from datetime import datetime

from django.db.models import Count, Sum

logger = logging.getLogger(__name__)


def _parse_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


class PaymentListCreateView(APIView):
    """
    POST /api/payments/  (app, cliente)
        Inicia el pago de una solicitud completada con cotización aceptada.
        Body: {"service_request_id": "...", "redirect_url": "adsapp://..."}
        El monto lo calcula el servidor; cualquier monto enviado se ignora.

    GET  /api/payments/  (panel admin)
        Lista paginada con resumen. Filtros: ?status=APPROVED&gateway=cash
        &service_request_id=...&date_from=2026-10-01&date_to=2026-10-31
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
        gateway_filter = request.query_params.get('gateway')
        if gateway_filter:
            payments = payments.filter(gateway=gateway_filter.lower())
        for param, lookup in (('date_from', 'created_at__date__gte'), ('date_to', 'created_at__date__lte')):
            raw = request.query_params.get(param)
            if raw:
                parsed = _parse_date(raw)
                if parsed is None:
                    return validation_error_response({param: ['Usa el formato AAAA-MM-DD']})
                payments = payments.filter(**{lookup: parsed})

        approved = payments.filter(status=Payment.STATUS_APPROVED)
        by_gateway = approved.values('gateway').annotate(count=Count('id'), total=Sum('amount_in_cents'))
        summary = {
            'approved_count': approved.count(),
            'approved_total_cop': (approved.aggregate(total=Sum('amount_in_cents'))['total'] or 0) // 100,
            'approved_by_gateway': {row['gateway']: {'count': row['count'], 'total_cop': row['total'] // 100}
                                    for row in by_gateway},
        }

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(payments, request, view=self)
        serializer = PaymentAdminListSerializer(page, many=True)

        return Response({
            'success': True,
            'count': paginator.page.paginator.count,
            'next': paginator.get_next_link(),
            'previous': paginator.get_previous_link(),
            'summary': summary,
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
