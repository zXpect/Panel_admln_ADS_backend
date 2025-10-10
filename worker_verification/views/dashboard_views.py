from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from ..services.worker_service import worker_service
from ..services.client_service import client_service
from ..services.document_service import document_service
import logging

logger = logging.getLogger(__name__)


class DashboardStatsView(APIView):
    """
    Vista para obtener estadísticas generales del dashboard
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        GET /api/dashboard/stats/
        Obtiene estadísticas generales del sistema
        
        Retorna:
        - Total de trabajadores
        - Trabajadores disponibles
        - Trabajadores en línea
        - Total de clientes
        - Documentos pendientes de revisión
        - Estadísticas por categoría
        """
        try:
            # Obtener estadísticas de trabajadores
            worker_stats = worker_service.get_workers_statistics()
            
            # Obtener total de clientes
            total_clients = client_service.count_clients()
            
            # Obtener documentos pendientes
            pending_docs = document_service.get_pending_documents()
            pending_count = len(pending_docs)
            
            # Agrupar documentos pendientes por tipo
            pending_by_type = {
                'hojaDeVida': 0,
                'antecedentesJudiciales': 0,
                'titulos': 0,
                'cartasRecomendacion': 0
            }
            
            for doc in pending_docs:
                category = doc.get('category', '')
                subcategory = doc.get('subcategory', '')
                
                if category == 'hojaDeVida':
                    pending_by_type['hojaDeVida'] += 1
                elif category == 'antecedentesJudiciales':
                    pending_by_type['antecedentesJudiciales'] += 1
                elif category == 'certificaciones':
                    if subcategory == 'titulos':
                        pending_by_type['titulos'] += 1
                    elif subcategory == 'cartasRecomendacion':
                        pending_by_type['cartasRecomendacion'] += 1
            
            stats = {
                'workers': {
                    'total': worker_stats['total'],
                    'available': worker_stats['available'],
                    'online': worker_stats['online'],
                    'byCategory': worker_stats['by_category']
                },
                'clients': {
                    'total': total_clients
                },
                'documents': {
                    'pendingTotal': pending_count,
                    'pendingByType': pending_by_type
                }
            }
            
            return Response({
                'success': True,
                'data': stats
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting dashboard stats: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)