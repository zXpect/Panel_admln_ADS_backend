import hmac
import logging

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from ..services.reminder_service import reminder_service
from .common import error_response

logger = logging.getLogger(__name__)


class RemindersRunView(APIView):
    """
    POST /api/internal/reminders/
    Header: X-Reminders-Token: <REMINDERS_TOKEN>

    Envía los recordatorios pendientes (HU-17). Lo llama un programador externo
    cada 30 minutos (.github/workflows/reminders.yml). Sin REMINDERS_TOKEN
    configurado la ruta no existe (404); con un token distinto, 403.
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'reminders'

    def post(self, request):
        expected = settings.REMINDERS_TOKEN
        if not expected:
            return error_response('No encontrado', status.HTTP_404_NOT_FOUND)
        received = request.headers.get('X-Reminders-Token', '')
        if not hmac.compare_digest(received.encode(), expected.encode()):
            return error_response('Token inválido', status.HTTP_403_FORBIDDEN)

        try:
            sent = reminder_service.run()
        except Exception:
            logger.exception('Error sending reminders')
            return error_response('No se pudieron enviar los recordatorios', status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({'success': True, 'data': sent})
