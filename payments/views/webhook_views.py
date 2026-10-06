from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..services.payment_service import EventResult, FirebaseSyncError, payment_service
import logging

logger = logging.getLogger(__name__)


class PaymentWebhookView(APIView):
    """
    POST /api/payments/webhook/
    Recibe los eventos de la pasarela (Wompi o el mock).

    No usa JWT ni sesión: la autenticidad se verifica con el checksum del
    evento (signature.checksum y header X-Event-Checksum). Wompi reintenta
    mientras la respuesta no sea 200.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            result = payment_service.process_event(
                request.data,
                header_checksum=request.headers.get('X-Event-Checksum'),
            )
        except FirebaseSyncError:
            # El pago ya quedó guardado; un 500 hace que la pasarela reintente
            # y el reintento vuelve a sincronizar Firebase.
            return Response({
                'success': False,
                'error': 'Error sincronizando el pago'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"Error processing payment event: {str(e)}")
            return Response({
                'success': False,
                'error': 'Error procesando el evento'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if result.outcome == EventResult.INVALID_CHECKSUM:
            return Response({
                'success': False,
                'error': 'Checksum inválido'
            }, status=status.HTTP_401_UNAUTHORIZED)

        if result.outcome == EventResult.MALFORMED:
            return Response({
                'success': False,
                'error': 'Evento inválido'
            }, status=status.HTTP_400_BAD_REQUEST)

        # applied, duplicate, ignored y unknown_reference se confirman con 200:
        # reintentarlos no cambiaría el resultado.
        return Response({
            'success': True,
            'data': {'outcome': result.outcome}
        }, status=status.HTTP_200_OK)
