from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from ..services.client_service import client_service
from ..serializers import ClientSerializer, ClientListSerializer
import logging

logger = logging.getLogger(__name__)


class ClientViewSet(viewsets.ViewSet):
    """
    ViewSet para operaciones con clientes
    """
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """
        GET /api/clients/
        Lista todos los clientes
        
        Query params:
        - search: Buscar por nombre o email
        """
        try:
            search = request.query_params.get('search')
            
            if search:
                clients = client_service.search_clients(search)
            else:
                clients = client_service.get_all_clients()
            
            serializer = ClientListSerializer(clients, many=True)
            
            return Response({
                'success': True,
                'count': len(clients),
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error listing clients: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def retrieve(self, request, pk=None):
        """
        GET /api/clients/{id}/
        Obtiene detalles de un cliente específico
        """
        try:
            client = client_service.get_client_by_id(pk)
            
            if not client:
                return Response({
                    'success': False,
                    'error': 'Cliente no encontrado'
                }, status=status.HTTP_404_NOT_FOUND)
            
            serializer = ClientSerializer(client)
            
            return Response({
                'success': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving client: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def count(self, request):
        """
        GET /api/clients/count/
        Obtiene el total de clientes
        """
        try:
            count = client_service.count_clients()
            
            return Response({
                'success': True,
                'count': count
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error counting clients: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)