import logging

from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from payments.authentication import FirebaseUser
from payments.permissions import IsAppOrPanelUser, IsAppUser, IsPanelUser
from payments.services.service_request_service import ServiceRequestError
from payments.views.common import APP_OR_PANEL_AUTHENTICATION, error_response, validation_error_response

from .models import PQR
from .serializers import PqrAdminSerializer, PqrAnswerSerializer, PqrCreateSerializer, PqrSerializer
from .services.pqr_service import pqr_service

logger = logging.getLogger(__name__)


def _serializer_for(user):
    return PqrSerializer if isinstance(user, FirebaseUser) else PqrAdminSerializer


class PqrListCreateView(APIView):
    """
    POST /api/pqr/   (app: cliente o trabajador de la solicitud)
        Body: {"service_request_id": "...", "type": "peticion|queja|reclamo", "description": "..."}
    GET  /api/pqr/?status=abierta
        App: las PQR propias. Panel: todas, paginadas.
    """
    authentication_classes = APP_OR_PANEL_AUTHENTICATION
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'pqr'

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAppUser()]
        return [IsAppOrPanelUser()]

    def get(self, request):
        pqrs = PQR.objects.select_related('responded_by')
        if isinstance(request.user, FirebaseUser):
            pqrs = pqrs.filter(author_uid=request.user.uid)
        status_filter = request.query_params.get('status')
        if status_filter:
            pqrs = pqrs.filter(status=status_filter)

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(pqrs, request, view=self)
        return Response({
            'success': True,
            'count': paginator.page.paginator.count,
            'next': paginator.get_next_link(),
            'previous': paginator.get_previous_link(),
            'data': _serializer_for(request.user)(page, many=True).data,
        })

    def post(self, request):
        serializer = PqrCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error_response(serializer.errors)
        try:
            pqr = pqr_service.create(request.user.uid, serializer.validated_data)
        except ServiceRequestError as e:
            return error_response(e.message, e.status_code)
        except Exception:
            logger.exception("Error creating PQR")
            return error_response('No se pudo registrar la PQR', status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({'success': True, 'data': PqrSerializer(pqr).data}, status=status.HTTP_201_CREATED)


class PqrDetailView(APIView):
    """
    GET   /api/pqr/<id>/   App (solo el autor) o panel
    PATCH /api/pqr/<id>/   Panel. Body: {"status": "en_tramite|cerrada", "response": "..."}
        Cerrar exige respuesta. Al responder se avisa al autor.
    """
    authentication_classes = APP_OR_PANEL_AUTHENTICATION
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'pqr'

    def get_permissions(self):
        if self.request.method == 'PATCH':
            return [IsPanelUser()]
        return [IsAppOrPanelUser()]

    def get(self, request, pk):
        pqr = PQR.objects.select_related('responded_by').filter(pk=pk).first()
        # 404 también si no es el autor: no se revela que la PQR existe
        if pqr is None or (isinstance(request.user, FirebaseUser) and pqr.author_uid != request.user.uid):
            return error_response('PQR no encontrada', status.HTTP_404_NOT_FOUND)
        return Response({'success': True, 'data': _serializer_for(request.user)(pqr).data})

    def patch(self, request, pk):
        serializer = PqrAnswerSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error_response(serializer.errors)
        try:
            pqr = pqr_service.answer(request.user, pk, serializer.validated_data)
        except ServiceRequestError as e:
            return error_response(e.message, e.status_code)
        return Response({'success': True, 'data': PqrAdminSerializer(pqr).data})
