import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from payments.permissions import IsAppUser
from payments.views.common import APP_AUTHENTICATION, validation_error_response

from ..serializers import EstimateSerializer
from ..services import pricing_service

logger = logging.getLogger(__name__)


class AppPricingView(APIView):
    """Base de los endpoints del catálogo para la app (ID token de Firebase)."""
    authentication_classes = APP_AUTHENTICATION
    permission_classes = [IsAppUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'service_requests'


class CatalogView(AppPricingView):
    """
    GET /api/catalog/
    Oficios y tareas activos con su unidad y el rango ajustado para Ubaté.

    Público (DEF-17): el trabajador elige oficios y tareas en el paso 2 del registro,
    antes de que exista su cuenta, y sin catálogo quedaba sin tareas. No trae datos
    personales. Ignora cualquier token para que uno vencido no lo bloquee; el límite
    de peticiones va por IP.
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = 'catalog'

    def get(self, request):
        return Response({'success': True, 'data': pricing_service.get_catalog()}, status=status.HTTP_200_OK)


class EstimateView(AppPricingView):
    """
    POST /api/requests/estimate/
    Body: {"service_category": "plomeria",
           "task_items": [{"task": "destapar-desague-sanitario", "quantity": 1},
                          {"custom_description": "...", "quantity": 1}]}
    Calcula el precio de referencia sin crear la solicitud.
    """

    def post(self, request):
        serializer = EstimateSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error_response(serializer.errors)

        estimate = pricing_service.estimate(serializer.validated_data['items'])
        return Response({'success': True, 'data': estimate}, status=status.HTTP_200_OK)
