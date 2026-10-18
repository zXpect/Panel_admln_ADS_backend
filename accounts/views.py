import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from payments.permissions import IsAppUser
from payments.services.service_request_service import ServiceRequestError
from payments.views.common import APP_AUTHENTICATION, error_response, is_valid_firebase_key
from worker_verification.services.firebase_service import firebase_service

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


class WorkerStatsView(APIView):
    """
    GET /api/workers/<worker_id>/stats/   (app)
    Trabajos realizados y calificación del trabajador para su perfil (B12).
    completed_jobs cuenta las solicitudes completed (con o sin calificación);
    no es lo mismo que totalRatings.
    """
    authentication_classes = APP_AUTHENTICATION
    permission_classes = [IsAppUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'service_requests'

    def get(self, request, worker_id):
        if not is_valid_firebase_key(worker_id):
            return error_response('ID de trabajador inválido', status.HTTP_400_BAD_REQUEST)
        try:
            worker = firebase_service.get_data(f"User/Trabajadores/{worker_id}")
            if not isinstance(worker, dict):
                return error_response('Trabajador no encontrado', status.HTTP_404_NOT_FOUND)
            requests = firebase_service.query_data('requests', order_by='worker_id', equal_to=worker_id) or {}
        except Exception:
            logger.exception(f"Error reading stats of worker {worker_id}")
            return error_response('No se pudieron consultar los datos', status.HTTP_500_INTERNAL_SERVER_ERROR)

        completed = sum(1 for item in requests.values()
                        if isinstance(item, dict) and item.get('status') == 'completed')
        return Response({'success': True, 'data': {
            'worker_id': worker_id,
            'completed_jobs': completed,
            'rating': worker.get('rating') or 0,
            'total_ratings': worker.get('totalRatings') or 0,
        }})
