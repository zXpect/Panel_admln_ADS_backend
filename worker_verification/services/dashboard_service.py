from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class DashboardService:
    """Servicio mejorado para manejar estadísticas del dashboard"""
    
    def __init__(self, firebase_service):
        self.firebase = firebase_service
        self.WORKERS_PATH = 'User/Trabajadores'
        self.DOCUMENTS_PATH = 'WorkerDocuments'  # CORREGIDO: path correcto
    
    def get_weekly_trends(self):
        """
        Calcula tendencias de los últimos 7 días de manera más precisa
        """
        try:
            today = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
            week_ago = (today - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
            
            days = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
            trends = []
            
            workers = self.firebase.get_data(self.WORKERS_PATH) or {}
            documents = self.firebase.get_data(self.DOCUMENTS_PATH) or {}
            
            logger.info(f"Calculando tendencias semanales - Workers: {len(workers)}, Documents: {len(documents)}")
            
            for i in range(7):
                current_day = week_ago + timedelta(days=i)
                day_start = current_day.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = current_day.replace(hour=23, minute=59, second=59, microsecond=999999)
                day_name = days[current_day.weekday()]
                
                # Contar actividad de trabajadores
                workers_active = self._count_workers_active_in_range(
                    workers, day_start, day_end
                )
                
                # Contar documentos procesados
                docs_processed = self._count_documents_processed_in_range(
                    documents, day_start, day_end
                )
                
                # Contar documentos subidos (para ver flujo de entrada)
                docs_uploaded = self._count_documents_uploaded_in_range(
                    documents, day_start, day_end
                )
                
                trends.append({
                    'day': day_name,
                    'workers': workers_active,
                    'documents': docs_processed,
                    'documentsUploaded': docs_uploaded,
                    'date': current_day.strftime('%Y-%m-%d')
                })
            
            logger.info(f"Tendencias semanales calculadas exitosamente: {len(trends)} días")
            return trends
            
        except Exception as e:
            logger.error(f"Error calculando tendencias semanales: {str(e)}", exc_info=True)
            return self._get_fallback_trends(days=7)
    
    def get_monthly_trends(self):
        """
        Calcula tendencias mensuales (últimos 30 días) agrupadas por semana
        """
        try:
            today = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
            month_ago = (today - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
            
            workers = self.firebase.get_data(self.WORKERS_PATH) or {}
            documents = self.firebase.get_data(self.DOCUMENTS_PATH) or {}
            
            # Agrupar por semanas
            weekly_data = []
            
            for week_num in range(5):  # 30 días = ~4-5 semanas
                week_start = month_ago + timedelta(days=week_num * 7)
                week_end = min(week_start + timedelta(days=6), today)
                
                if week_start > today:
                    break
                
                workers_active = self._count_workers_active_in_range(
                    workers, week_start, week_end
                )
                
                docs_processed = self._count_documents_processed_in_range(
                    documents, week_start, week_end
                )
                
                docs_uploaded = self._count_documents_uploaded_in_range(
                    documents, week_start, week_end
                )
                
                weekly_data.append({
                    'week': f"Sem {week_num + 1}",
                    'workers': workers_active,
                    'documents': docs_processed,
                    'documentsUploaded': docs_uploaded,
                    'startDate': week_start.strftime('%Y-%m-%d'),
                    'endDate': week_end.strftime('%Y-%m-%d')
                })
            
            logger.info(f"Tendencias mensuales calculadas: {len(weekly_data)} semanas")
            return weekly_data
            
        except Exception as e:
            logger.error(f"Error calculando tendencias mensuales: {str(e)}", exc_info=True)
            return []
    
    def _count_workers_active_in_range(self, workers, start_time, end_time):
        """
        Cuenta trabajadores que estuvieron activos en un rango de tiempo.
        Se considera activo si:
        - Tiene timestamp de actividad en el rango
        - Tiene lastOnline en el rango
        - Está actualmente online (para días recientes)
        """
        count = 0
        start_ts = int(start_time.timestamp() * 1000)
        end_ts = int(end_time.timestamp() * 1000)
        
        for worker_id, worker_data in workers.items():
            if not isinstance(worker_data, dict):
                continue
            
            is_active = False
            
            # 1. Verificar timestamp de actualización
            timestamp = worker_data.get('timestamp')
            if timestamp and self._is_timestamp_in_range(timestamp, start_ts, end_ts):
                is_active = True
            
            # 2. Verificar lastOnline
            if not is_active:
                last_online = worker_data.get('lastOnline')
                if last_online and self._is_timestamp_in_range(last_online, start_ts, end_ts):
                    is_active = True
            
            # 3. Si está online ahora y estamos revisando hoy/ayer
            if not is_active:
                now = datetime.now()
                if (end_time.date() >= (now - timedelta(days=1)).date() and 
                    worker_data.get('isOnline', False)):
                    is_active = True
            
            if is_active:
                count += 1
        
        return count
    
    def _count_documents_processed_in_range(self, documents, start_time, end_time):
        """
        Cuenta documentos procesados (aprobados/rechazados) en un rango de tiempo
        """
        count = 0
        start_ts = int(start_time.timestamp() * 1000)
        end_ts = int(end_time.timestamp() * 1000)
        
        for worker_id, worker_docs in documents.items():
            if not isinstance(worker_docs, dict):
                continue
            
            count += self._count_processed_in_category(
                worker_docs, start_ts, end_ts
            )
        
        return count
    
    def _count_documents_uploaded_in_range(self, documents, start_time, end_time):
        """
        Cuenta documentos SUBIDOS en un rango de tiempo
        """
        count = 0
        start_ts = int(start_time.timestamp() * 1000)
        end_ts = int(end_time.timestamp() * 1000)
        
        for worker_id, worker_docs in documents.items():
            if not isinstance(worker_docs, dict):
                continue
            
            count += self._count_uploaded_in_category(
                worker_docs, start_ts, end_ts
            )
        
        return count
    
    def _count_processed_in_category(self, category_data, start_ts, end_ts):
        """
        Cuenta recursivamente documentos procesados en una categoría
        """
        count = 0
        
        for key, value in category_data.items():
            if not isinstance(value, dict):
                continue
            
            # Si tiene reviewedAt, es un documento
            if 'reviewedAt' in value and 'status' in value:
                reviewed_at = value.get('reviewedAt')
                status_val = value.get('status')
                
                if (status_val in ['approved', 'rejected'] and 
                    reviewed_at and 
                    self._is_timestamp_in_range(reviewed_at, start_ts, end_ts)):
                    count += 1
            
            # Si no, puede ser una categoría anidada (certificaciones)
            else:
                count += self._count_processed_in_category(value, start_ts, end_ts)
        
        return count
    
    def _count_uploaded_in_category(self, category_data, start_ts, end_ts):
        """
        Cuenta recursivamente documentos subidos en una categoría
        """
        count = 0
        
        for key, value in category_data.items():
            if not isinstance(value, dict):
                continue
            
            # Si tiene uploadedAt, es un documento
            if 'uploadedAt' in value:
                uploaded_at = value.get('uploadedAt')
                
                if uploaded_at and self._is_timestamp_in_range(uploaded_at, start_ts, end_ts):
                    count += 1
            
            # Si no, puede ser una categoría anidada
            else:
                count += self._count_uploaded_in_category(value, start_ts, end_ts)
        
        return count
    
    def _is_timestamp_in_range(self, timestamp, start_ts, end_ts):
        """
        Verifica si un timestamp está dentro del rango
        Maneja diferentes formatos de timestamp
        """
        try:
            if isinstance(timestamp, (int, float)):
                # Firebase usa milisegundos
                ts = int(timestamp)
                return start_ts <= ts <= end_ts
            elif isinstance(timestamp, str):
                # Intentar parsear string ISO
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                ts = int(dt.timestamp() * 1000)
                return start_ts <= ts <= end_ts
        except Exception as e:
            logger.debug(f"Error parseando timestamp {timestamp}: {e}")
            return False
        
        return False
    
    def _get_fallback_trends(self, days=7):
        """
        Retorna datos de respaldo si no se pueden calcular las tendencias
        """
        day_names = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
        today = datetime.now()
        
        trends = []
        for i in range(days):
            date = today - timedelta(days=days - 1 - i)
            day_name = day_names[date.weekday()] if days == 7 else f"Día {i+1}"
            
            trends.append({
                'day': day_name,
                'workers': 0,
                'documents': 0,
                'documentsUploaded': 0,
                'date': date.strftime('%Y-%m-%d')
            })
        
        logger.warning("Usando datos de respaldo para tendencias")
        return trends
    
    def get_detailed_activity_stats(self):
        """
        Obtiene estadísticas detalladas de actividad para análisis profundo
        """
        try:
            workers = self.firebase.get_data(self.WORKERS_PATH) or {}
            documents = self.firebase.get_data(self.DOCUMENTS_PATH) or {}
            
            now = datetime.now()
            last_24h = now - timedelta(hours=24)
            last_7d = now - timedelta(days=7)
            last_30d = now - timedelta(days=30)
            
            last_24h_ts = int(last_24h.timestamp() * 1000)
            last_7d_ts = int(last_7d.timestamp() * 1000)
            last_30d_ts = int(last_30d.timestamp() * 1000)
            now_ts = int(now.timestamp() * 1000)
            
            stats = {
                'workers': {
                    'active_24h': self._count_workers_active_in_range(
                        workers, last_24h, now
                    ),
                    'active_7d': self._count_workers_active_in_range(
                        workers, last_7d, now
                    ),
                    'active_30d': self._count_workers_active_in_range(
                        workers, last_30d, now
                    )
                },
                'documents': {
                    'processed_24h': self._count_documents_processed_in_range(
                        documents, last_24h, now
                    ),
                    'processed_7d': self._count_documents_processed_in_range(
                        documents, last_7d, now
                    ),
                    'processed_30d': self._count_documents_processed_in_range(
                        documents, last_30d, now
                    ),
                    'uploaded_24h': self._count_documents_uploaded_in_range(
                        documents, last_24h, now
                    ),
                    'uploaded_7d': self._count_documents_uploaded_in_range(
                        documents, last_7d, now
                    ),
                    'uploaded_30d': self._count_documents_uploaded_in_range(
                        documents, last_30d, now
                    )
                }
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas detalladas: {str(e)}", exc_info=True)
            return None


# Instancia global del servicio
from .firebase_service import firebase_service
dashboard_service = DashboardService(firebase_service)