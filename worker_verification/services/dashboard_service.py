from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class DashboardService:
    """Servicio para manejar estadísticas del dashboard"""
    
    def __init__(self, firebase_service):
        self.firebase = firebase_service
        self.WORKERS_PATH = 'User/Trabajadores'
        self.DOCUMENTS_PATH = 'workerDocuments'
    
    def get_weekly_trends(self):
        """
        Calcula tendencias de los últimos 7 días
        Retorna datos de trabajadores en línea y documentos procesados por día
        """
        try:
            # Obtener fecha actual y hace 7 días
            today = datetime.now()
            week_ago = today - timedelta(days=7)
            
            # Inicializar estructura de datos para los 7 días
            days = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
            trends = []
            
            workers = self.firebase.get_data(self.WORKERS_PATH) or {}
            
            documents = self.firebase.get_data(self.DOCUMENTS_PATH) or {}
            
            logger.info(f"Workers found: {len(workers)}, Documents found: {len(documents)}")
            
            # Calcular para cada día de la semana
            for i in range(7):
                current_day = week_ago + timedelta(days=i)
                day_name = days[current_day.weekday()]
                
                # Contar trabajadores que estuvieron en línea ese día
                workers_online = self._count_workers_online_on_day(workers, current_day)
                
                # Contar documentos procesados (aprobados o rechazados) ese día
                docs_processed = self._count_documents_processed_on_day(documents, current_day)
                
                trends.append({
                    'day': day_name,
                    'workers': workers_online,
                    'documents': docs_processed,
                    'date': current_day.strftime('%Y-%m-%d')
                })
            
            logger.info(f"Weekly trends calculated: {trends}")
            return trends
            
        except Exception as e:
            logger.error(f"Error calculating weekly trends: {str(e)}", exc_info=True)
            # Retornar datos de respaldo si hay error
            return self._get_fallback_trends()
    
    def _count_workers_online_on_day(self, workers, target_day):
        """
        Cuenta trabajadores que estuvieron en línea en un día específico
        """
        count = 0
        target_date = target_day.date()
        
        for worker_id, worker_data in workers.items():
            if not isinstance(worker_data, dict):
                continue
            
            # Si tiene registro de última conexión
            last_online = worker_data.get('lastOnline')
            if last_online:
                try:
                    # Convertir timestamp a fecha
                    if isinstance(last_online, (int, float)):
                        online_date = datetime.fromtimestamp(last_online / 1000).date()
                    else:
                        online_date = datetime.fromisoformat(str(last_online)).date()
                    
                    if online_date == target_date:
                        count += 1
                except Exception as e:
                    logger.debug(f"Error parsing lastOnline for worker {worker_id}: {e}")
                    continue
            
            # Si actualmente está en línea y no tiene registro de última conexión
            elif worker_data.get('isOnline', False):
                count += 1
        
        return count
    
    def _count_documents_processed_on_day(self, documents, target_day):
        """
        Cuenta documentos procesados (aprobados/rechazados) en un día específico
        """
        count = 0
        target_date = target_day.date()
        
        for worker_id, worker_docs in documents.items():
            if not isinstance(worker_docs, dict):
                continue
            
            # Revisar todas las categorías de documentos
            for category, category_data in worker_docs.items():
                if not isinstance(category_data, dict):
                    continue
                
                # Manejar documentos únicos (hoja_de_vida, antecedentes_judiciales)
                if 'reviewedAt' in category_data:
                    count += self._check_document_reviewed_on_day(category_data, target_date)
                
                # Manejar colecciones de documentos (certificaciones)
                else:
                    for doc_id, doc_data in category_data.items():
                        if isinstance(doc_data, dict) and 'reviewedAt' in doc_data:
                            count += self._check_document_reviewed_on_day(doc_data, target_date)
        
        return count
    
    def _check_document_reviewed_on_day(self, doc_data, target_date):
        """
        Verifica si un documento fue revisado en la fecha objetivo
        """
        reviewed_at = doc_data.get('reviewedAt')
        status = doc_data.get('status')
        
        if reviewed_at and status in ['approved', 'rejected']:
            try:
                if isinstance(reviewed_at, (int, float)):
                    review_date = datetime.fromtimestamp(reviewed_at / 1000).date()
                else:
                    review_date = datetime.fromisoformat(str(reviewed_at)).date()
                
                if review_date == target_date:
                    return 1
            except Exception as e:
                logger.debug(f"Error parsing reviewedAt: {e}")
                pass
        
        return 0
    
    def _get_fallback_trends(self):
        """
        Retorna datos de respaldo si no se pueden calcular las tendencias reales
        """
        days = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
        today = datetime.now()
        
        trends = []
        for i, day in enumerate(days):
            date = today - timedelta(days=6-i)
            trends.append({
                'day': day,
                'workers': 0,
                'documents': 0,
                'date': date.strftime('%Y-%m-%d')
            })
        
        logger.warning("Using fallback trends data")
        return trends
    
    def get_monthly_trends(self):
        """
        Calcula tendencias mensuales (últimos 30 días)
        """
        try:
            today = datetime.now()
            month_ago = today - timedelta(days=30)
            
            # CORREGIDO: Usar rutas correctas
            workers = self.firebase.get_data(self.WORKERS_PATH) or {}
            documents = self.firebase.get_data(self.DOCUMENTS_PATH) or {}
            
            # Agrupar por semana
            weekly_data = defaultdict(lambda: {'workers': 0, 'documents': 0})
            
            for i in range(30):
                current_day = month_ago + timedelta(days=i)
                week_number = f"Semana {(i // 7) + 1}"
                
                workers_count = self._count_workers_online_on_day(workers, current_day)
                docs_count = self._count_documents_processed_on_day(documents, current_day)
                
                weekly_data[week_number]['workers'] += workers_count
                weekly_data[week_number]['documents'] += docs_count
            
            trends = [
                {
                    'week': week,
                    'workers': data['workers'],
                    'documents': data['documents']
                }
                for week, data in weekly_data.items()
            ]
            
            return trends
            
        except Exception as e:
            logger.error(f"Error calculating monthly trends: {str(e)}", exc_info=True)
            return []


# Instancia global del servicio
from .firebase_service import firebase_service
dashboard_service = DashboardService(firebase_service)