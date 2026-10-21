import copy
import logging

from django.db import transaction
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from payments.permissions import IsPanelUser
from payments.views.common import error_response, validation_error_response
from worker_verification.models import SystemConfig

from ..models import ConfigAuditLog, ServiceCategory, Task
from ..serializers.admin_serializers import AdminCategorySerializer, AdminConfigSerializer, AdminTaskSerializer
from ..services.config_audit_service import config_audit_service

logger = logging.getLogger(__name__)


class PanelView(APIView):
    """Base de las rutas del panel (B10): solo JWT del panel; el token de la app recibe 401/403."""
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsPanelUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'panel'

    def save_audited(self, serializer, old_instance):
        """Guarda el cambio y su registro de ConfigAuditLog en la misma transacción (I10)."""
        with transaction.atomic():
            instance = serializer.save()
            config_audit_service.log_change(self.request.user, old_instance, instance)
        return instance


class AdminCatalogView(PanelView):
    """
    GET /api/admin/catalog/
    Oficios y tareas, incluidos los inactivos, con la referencia de ciudades
    grandes (sin el factor regional).
    """

    def get(self, request):
        categories = ServiceCategory.objects.prefetch_related('tasks').order_by('order', 'name')
        return Response({'success': True, 'data': AdminCategorySerializer(categories, many=True).data})


class AdminCategoryDetailView(PanelView):
    """PATCH /api/admin/catalog/categories/<id>/   Body: {"name", "is_active", "order"}"""

    def patch(self, request, pk):
        category = ServiceCategory.objects.filter(pk=pk).first()
        if category is None:
            return error_response('Oficio no encontrado', status.HTTP_404_NOT_FOUND)
        old = copy.copy(category)
        serializer = AdminCategorySerializer(category, data=request.data, partial=True)
        if not serializer.is_valid():
            return validation_error_response(serializer.errors)
        category = self.save_audited(serializer, old)
        return Response({'success': True, 'data': AdminCategorySerializer(category).data})


class AdminTaskCreateView(PanelView):
    """
    POST /api/admin/catalog/tasks/
    Body: {"category": "plomeria", "slug": "...", "name": "...", "unit": "visita",
           "reference_min_cop": 40000, "reference_max_cop": 90000, "source": "...", "order": 9}
    """

    def post(self, request):
        serializer = AdminTaskSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error_response(serializer.errors)
        task = self.save_audited(serializer, None)
        return Response({'success': True, 'data': AdminTaskSerializer(task).data}, status=status.HTTP_201_CREATED)


class AdminTaskDetailView(PanelView):
    """
    PATCH /api/admin/catalog/tasks/<id>/
    Cualquier campo de la tarea, incluido is_active. No se borran: se desactivan.
    El quote_reference ya congelado en las solicitudes no cambia.
    """

    def patch(self, request, pk):
        task = Task.objects.select_related('category').filter(pk=pk).first()
        if task is None:
            return error_response('Tarea no encontrada', status.HTTP_404_NOT_FOUND)
        old = copy.copy(task)
        serializer = AdminTaskSerializer(task, data=request.data, partial=True)
        if not serializer.is_valid():
            return validation_error_response(serializer.errors)
        task = self.save_audited(serializer, old)
        return Response({'success': True, 'data': AdminTaskSerializer(task).data})


class AdminConfigListView(PanelView):
    """GET /api/admin/config/   Parámetros de cotización y búsqueda."""

    def get(self, request):
        configs = SystemConfig.objects.order_by('key')
        return Response({'success': True, 'data': AdminConfigSerializer(configs, many=True).data})


class AdminConfigDetailView(PanelView):
    """PATCH /api/admin/config/<key>/   Body: {"value": "27000"}"""

    def patch(self, request, key):
        config = SystemConfig.objects.filter(key=key).first()
        if config is None:
            return error_response('Parámetro no encontrado', status.HTTP_404_NOT_FOUND)
        if 'value' not in request.data:
            return validation_error_response({'value': ['Este campo es requerido.']})
        old = copy.copy(config)
        serializer = AdminConfigSerializer(config, data={'value': request.data['value']}, partial=True)
        if not serializer.is_valid():
            return validation_error_response(serializer.errors)
        config = self.save_audited(serializer, old)
        return Response({'success': True, 'data': AdminConfigSerializer(config).data})


class AdminAuditLogView(PanelView):
    """
    GET /api/admin/audit/?entity=Task
    Historial de cambios de oficios, tareas, parámetros (I10) y cuentas
    (entity=Account), del más reciente al más antiguo.
    """

    def get(self, request):
        logs = ConfigAuditLog.objects.select_related('admin')
        entity = request.query_params.get('entity')
        if entity:
            logs = logs.filter(entity=entity)

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(logs, request, view=self)
        data = [{
            'id': log.id,
            'admin': log.admin.username,
            'entity': log.entity,
            'entity_key': log.entity_key,
            'old_value': log.old_value,
            'new_value': log.new_value,
            'created_at': log.created_at,
        } for log in page]
        return Response({
            'success': True,
            'count': paginator.page.paginator.count,
            'next': paginator.get_next_link(),
            'previous': paginator.get_previous_link(),
            'data': data,
        })
