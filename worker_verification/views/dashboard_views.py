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
            
            # Obtener estadísticas de documentos
            document_stats = document_service.get_documents_statistics()
            
            # Obtener estadísticas de actividad detalladas
            activity_stats = dashboard_service.get_detailed_activity_stats()
            
            # Obtener documentos pendientes (para desglose por tipo)
            pending_docs = document_service.get_pending_documents()
            
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
                    'verified': worker_stats['verified'],
                    'available': worker_stats['available'],
                    'online': worker_stats['online'],
                    'byCategory': worker_stats['by_category']
                },
                'clients': {
                    'total': total_clients
                },
                'documents': {
                    'total': document_stats['total'],
                    'pending': document_stats['pending'],
                    'approved': document_stats['approved'],
                    'rejected': document_stats['rejected'],
                    'processed': document_stats['processed'],
                    'pendingByType': pending_by_type
                },
                'activity': activity_stats  # Nuevas estadísticas de actividad
            }
            
            logger.info("Estadísticas del dashboard obtenidas exitosamente")
            return Response({
                'success': True,
                'data': stats
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas del dashboard: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Error al obtener estadísticas del dashboard',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DashboardWeeklyTrendsView(APIView):
    """
    Vista para obtener tendencias semanales mejoradas
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        GET /api/dashboard/weekly-trends/
        Obtiene tendencias de los últimos 7 días
        
        Retorna:
        - Trabajadores activos por día
        - Documentos procesados por día
        - Documentos subidos por día
        """
        try:
            trends = dashboard_service.get_weekly_trends()
            
            # Calcular métricas adicionales
            total_workers = sum(day['workers'] for day in trends)
            total_docs_processed = sum(day['documents'] for day in trends)
            total_docs_uploaded = sum(day['documentsUploaded'] for day in trends)
            
            avg_workers = total_workers / len(trends) if trends else 0
            avg_docs_processed = total_docs_processed / len(trends) if trends else 0
            avg_docs_uploaded = total_docs_uploaded / len(trends) if trends else 0
            
            response_data = {
                'trends': trends,
                'summary': {
                    'totalWorkersActive': total_workers,
                    'totalDocsProcessed': total_docs_processed,
                    'totalDocsUploaded': total_docs_uploaded,
                    'avgWorkersPerDay': round(avg_workers, 1),
                    'avgDocsProcessedPerDay': round(avg_docs_processed, 1),
                    'avgDocsUploadedPerDay': round(avg_docs_uploaded, 1),
                    'period': '7 días'
                }
            }
            
            logger.info(f"Tendencias semanales obtenidas: {len(trends)} días")
            return Response({
                'success': True,
                'data': response_data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error obteniendo tendencias semanales: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Error al obtener tendencias semanales',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DashboardMonthlyTrendsView(APIView):
    """
    Vista para obtener tendencias mensuales mejoradas
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        GET /api/dashboard/monthly-trends/
        Obtiene tendencias de los últimos 30 días agrupadas por semana
        """
        try:
            trends = dashboard_service.get_monthly_trends()
            
            # Calcular métricas adicionales
            total_workers = sum(week['workers'] for week in trends)
            total_docs_processed = sum(week['documents'] for week in trends)
            total_docs_uploaded = sum(week['documentsUploaded'] for week in trends)
            
            avg_workers = total_workers / len(trends) if trends else 0
            avg_docs_processed = total_docs_processed / len(trends) if trends else 0
            avg_docs_uploaded = total_docs_uploaded / len(trends) if trends else 0
            
            # Encontrar semana con mayor actividad
            peak_week = max(trends, key=lambda x: x['workers'] + x['documents']) if trends else None
            
            response_data = {
                'trends': trends,
                'summary': {
                    'totalWorkersActive': total_workers,
                    'totalDocsProcessed': total_docs_processed,
                    'totalDocsUploaded': total_docs_uploaded,
                    'avgWorkersPerWeek': round(avg_workers, 1),
                    'avgDocsProcessedPerWeek': round(avg_docs_processed, 1),
                    'avgDocsUploadedPerWeek': round(avg_docs_uploaded, 1),
                    'peakWeek': peak_week['week'] if peak_week else None,
                    'period': '30 días'
                }
            }
            
            logger.info(f"Tendencias mensuales obtenidas: {len(trends)} semanas")
            return Response({
                'success': True,
                'data': response_data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error obteniendo tendencias mensuales: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Error al obtener tendencias mensuales',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DashboardActivityStatsView(APIView):
    """
    Vista para obtener estadísticas detalladas de actividad
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        GET /api/dashboard/activity-stats/
        Obtiene estadísticas de actividad en diferentes períodos
        """
        try:
            stats = dashboard_service.get_detailed_activity_stats()
            
            if not stats:
                return Response({
                    'success': False,
                    'error': 'No se pudieron obtener estadísticas de actividad'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            logger.info("Estadísticas de actividad obtenidas exitosamente")
            return Response({
                'success': True,
                'data': stats
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas de actividad: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Error al obtener estadísticas de actividad',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)