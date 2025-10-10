from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from ..services.worker_service import worker_service
from ..serializers import (
    WorkerSerializer,
    WorkerUpdateSerializer,
    WorkerAvailabilitySerializer,
    WorkerOnlineStatusSerializer,
    WorkerVerificationStatusSerializer,
    WorkerLocationSerializer,
    WorkerRatingSerializer,
    WorkerStatisticsSerializer,
)
import logging

logger = logging.getLogger(__name__)


class WorkerViewSet(viewsets.ViewSet):
    """
    ViewSet para operaciones con trabajadores
    """
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """
        GET /api/workers/
        Lista todos los trabajadores
        
        Query params:
        - category: Filtrar por categoría
        - available: Filtrar por disponibilidad (true/false)
        - online: Filtrar por estado en línea (true/false)
        - search: Buscar por nombre, apellido o categoría
        """
        try:
            # Obtener parámetros de filtro
            category = request.query_params.get('category')
            available = request.query_params.get('available')
            online = request.query_params.get('online')
            search = request.query_params.get('search')
            
            # Aplicar filtros
            if search:
                workers = worker_service.search_workers(search)
            elif category:
                workers = worker_service.get_workers_by_category(category)
            elif available == 'true':
                workers = worker_service.get_available_workers()
            elif online == 'true':
                workers = worker_service.get_online_workers()
            else:
                workers = worker_service.get_all_workers()
            
            serializer = WorkerSerializer(workers, many=True)
            
            return Response({
                'success': True,
                'count': len(workers),
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error listing workers: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def retrieve(self, request, pk=None):
        """
        GET /api/workers/{id}/
        Obtiene detalles de un trabajador específico
        """
        try:
            worker = worker_service.get_worker_by_id(pk)
            
            if not worker:
                return Response({
                    'success': False,
                    'error': 'Trabajador no encontrado'
                }, status=status.HTTP_404_NOT_FOUND)
            
            serializer = WorkerSerializer(worker)
            
            return Response({
                'success': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving worker: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def create(self, request):
        """
        POST /api/workers/
        Crea un nuevo trabajador
        """
        try:
            serializer = WorkerSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            worker = worker_service.create_worker(serializer.validated_data)
            
            return Response({
                'success': True,
                'message': 'Trabajador creado exitosamente',
                'data': WorkerSerializer(worker).data
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error creating worker: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def update(self, request, pk=None):
        """
        PUT /api/workers/{id}/
        Actualiza un trabajador completamente
        """
        try:
            # Verificar que existe
            if not worker_service.worker_exists(pk):
                return Response({
                    'success': False,
                    'error': 'Trabajador no encontrado'
                }, status=status.HTTP_404_NOT_FOUND)
            
            serializer = WorkerSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            worker_service.update_worker(pk, serializer.validated_data)
            
            return Response({
                'success': True,
                'message': 'Trabajador actualizado exitosamente'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error updating worker: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def partial_update(self, request, pk=None):
        """
        PATCH /api/workers/{id}/
        Actualiza campos específicos de un trabajador
        """
        try:
            # Verificar que existe
            if not worker_service.worker_exists(pk):
                return Response({
                    'success': False,
                    'error': 'Trabajador no encontrado'
                }, status=status.HTTP_404_NOT_FOUND)
            
            serializer = WorkerUpdateSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            worker_service.update_worker(pk, serializer.validated_data)
            
            return Response({
                'success': True,
                'message': 'Trabajador actualizado exitosamente'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error partially updating worker: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def destroy(self, request, pk=None):
        """
        DELETE /api/workers/{id}/
        Elimina un trabajador
        """
        try:
            # Verificar que existe
            if not worker_service.worker_exists(pk):
                return Response({
                    'success': False,
                    'error': 'Trabajador no encontrado'
                }, status=status.HTTP_404_NOT_FOUND)
            
            worker_service.delete_worker(pk)
            
            return Response({
                'success': True,
                'message': 'Trabajador eliminado exitosamente'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error deleting worker: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['patch'])
    def availability(self, request, pk=None):
        """
        PATCH /api/workers/{id}/availability/
        Actualiza la disponibilidad de un trabajador
        
        Body: {"isAvailable": true/false}
        """
        try:
            serializer = WorkerAvailabilitySerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            worker_service.update_worker_availability(
                pk,
                serializer.validated_data['isAvailable']
            )
            
            return Response({
                'success': True,
                'message': 'Disponibilidad actualizada exitosamente'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error updating availability: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['patch'])
    def online_status(self, request, pk=None):
        """
        PATCH /api/workers/{id}/online_status/
        Actualiza el estado en línea de un trabajador
        
        Body: {"isOnline": true/false}
        """
        try:
            serializer = WorkerOnlineStatusSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            worker_service.update_worker_online_status(
                pk,
                serializer.validated_data['isOnline']
            )
            
            return Response({
                'success': True,
                'message': 'Estado en línea actualizado exitosamente'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error updating online status: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    @action(detail=True, methods=["patch"], url_path="verification_status")
    def update_verification_status(self, request, pk=None):
        """
        Actualiza el estado de verificación de un trabajador
        """
        serializer = WorkerVerificationStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        worker = worker_service.get_worker_by_id(pk)
        if not worker:
            return Response({"error": "Worker not found"}, status=status.HTTP_404_NOT_FOUND)

    # estado actual
        current_status = worker.get("verificationStatus", {})

    # Solo actualizar status, conservar lo demás (ej: submittedAt)
        updated_status = {**current_status, **serializer.validated_data}

        worker["verificationStatus"] = updated_status
        worker_service.update_worker(pk, worker)

        return Response({
        "message": "Verification status updated successfully",
        "verificationStatus": updated_status
    })
    
    @action(detail=True, methods=['patch'])
    def location(self, request, pk=None):
        """
        PATCH /api/workers/{id}/location/
        Actualiza la ubicación de un trabajador
        
        Body: {"latitude": 5.34851, "longitude": -73.902605}
        """
        try:
            serializer = WorkerLocationSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            worker_service.update_worker_location(
                pk,
                serializer.validated_data['latitude'],
                serializer.validated_data['longitude']
            )
            
            return Response({
                'success': True,
                'message': 'Ubicación actualizada exitosamente'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error updating location: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def add_rating(self, request, pk=None):
        """
        POST /api/workers/{id}/add_rating/
        Agrega una nueva calificación al trabajador
        
        Body: {"rating": 4.5}
        """
        try:
            serializer = WorkerRatingSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            worker_service.update_worker_rating(
                pk,
                serializer.validated_data['rating']
            )
            
            return Response({
                'success': True,
                'message': 'Calificación agregada exitosamente'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error adding rating: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        GET /api/workers/statistics/
        Obtiene estadísticas generales de trabajadores
        """
        try:
            stats = worker_service.get_workers_statistics()
            serializer = WorkerStatisticsSerializer(stats)
            
            return Response({
                'success': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting statistics: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)