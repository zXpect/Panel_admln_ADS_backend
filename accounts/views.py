import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from payments.permissions import IsAppUser
from payments.services.service_request_service import ServiceRequestError
from payments.views.common import APP_AUTHENTICATION, error_response

from .services.account_service import account_service

logger = logging.getLogger(__name__)


class MeView(APIView):
    """
    DELETE /api/me/   (app)
    Elimina la cuenta del usuario y sus datos personales (D18). 409 si tiene
    un servicio en camino o en progreso.
    """
    authentication_classes = APP_AUTHENTICATION
    permission_classes = [IsAppUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'account'

    def delete(self, request):
        try:
            account_service.delete_account(request.user.uid)
        except ServiceRequestError as e:
            return error_response(e.message, e.status_code)
        except Exception:
            logger.exception(f"Error deleting account {request.user.uid}")
            return error_response('No se pudo eliminar la cuenta; intenta de nuevo',
                                  status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(status=status.HTTP_204_NO_CONTENT)
