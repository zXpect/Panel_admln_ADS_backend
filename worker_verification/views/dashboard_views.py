from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from ..services.worker_service import worker_service
from ..services.client_service import client_service
from ..services.document_service import document_service
from ..services.dashboard_service import dashboard_service
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
            
            # NUEVO: Contar trabajadores con documentos pendientes (trabajadores NO verificados)
            workers_with_pending_docs = set()
            
            for doc in pending_docs:
                category = doc.get('category', '')
                subcategory = doc.get('subcategory', '')
                worker_id = doc.get('workerId', '')
                
                # Agregar trabajador al set de no verificados
                if worker_id:
                    workers_with_pending_docs.add(worker_id)
                
                if category == 'hojaDeVida':
                    pending_by_type['hojaDeVida'] += 1
                elif category == 'antecedentesJudiciales':
                    pending_by_type['antecedentesJudiciales'] += 1
                elif category == 'certificaciones':
                    if subcategory == 'titulos':
                        pending_by_type['titulos'] += 1
                    elif subcategory == 'cartasRecomendacion':
                        pending_by_type['cartasRecomendacion'] += 1
            
            # NUEVO: Calcular trabajadores verificados correctamente
            total_workers = worker_stats['total']
            workers_not_verified = len(workers_with_pending_docs)
            workers_verified = max(0, total_workers - workers_not_verified)
            
            stats = {
                'workers': {
                    'total': total_workers,
                    'available': worker_stats['available'],
                    'online': worker_stats['online'],
                    'verified': workers_verified,  # NUEVO: Trabajadores verificados
                    'notVerified': workers_not_verified,  # NUEVO: Trabajadores no verificados
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
            
            logger.info(f"Dashboard stats calculated: {workers_verified} verified workers out of {total_workers}")
            
            return Response({
                'success': True,
                'data': stats
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting dashboard stats: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DashboardWeeklyTrendsView(APIView):
    """
    Vista para obtener tendencias semanales
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        GET /api/dashboard/weekly-trends/
        Obtiene tendencias de los últimos 7 días
        
        Retorna:
        - Trabajadores en línea por día
        - Documentos procesados por día
        """
        try:
            trends = dashboard_service.get_weekly_trends()
            
            return Response({
                'success': True,
                'data': trends
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting weekly trends: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DashboardMonthlyTrendsView(APIView):
    """
    Vista para obtener tendencias mensuales
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        GET /api/dashboard/monthly-trends/
        Obtiene tendencias de los últimos 30 días agrupadas por semana
        """
        try:
            trends = dashboard_service.get_monthly_trends()
            
            return Response({
                'success': True,
                'data': trends
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting monthly trends: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)