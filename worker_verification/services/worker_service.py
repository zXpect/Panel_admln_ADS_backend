from .firebase_service import firebase_service
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class WorkerService:
    """
    Servicio para manejar operaciones relacionadas con trabajadores
    """
    
    WORKERS_PATH = 'User/Trabajadores'
    ACTIVE_WORKERS_PATH = 'active_workers'
    
    def __init__(self):
        self.firebase = firebase_service
    
    def get_all_workers(self):
        """
        Obtiene todos los trabajadores
        
        Returns:
            dict: Diccionario con todos los trabajadores
        """
        try:
            workers = self.firebase.get_data(self.WORKERS_PATH)
            
            if not workers:
                return {}
            
            # Convertir a lista para facilitar el manejo
            workers_list = []
            for worker_id, worker_data in workers.items():
                worker_data['id'] = worker_id
                workers_list.append(worker_data)
            
            logger.info(f"Retrieved {len(workers_list)} workers")
            return workers_list
        except Exception as e:
            logger.error(f"Error getting all workers: {str(e)}")
            raise
    
    def get_worker_by_id(self, worker_id):
        """
        Obtiene un trabajador por su ID
        
        Args:
            worker_id (str): ID del trabajador
            
        Returns:
            dict: Datos del trabajador
        """
        try:
            path = f"{self.WORKERS_PATH}/{worker_id}"
            worker = self.firebase.get_data(path)
            
            if worker:
                worker['id'] = worker_id
                logger.info(f"Retrieved worker {worker_id}")
            else:
                logger.warning(f"Worker {worker_id} not found")
            
            return worker
        except Exception as e:
            logger.error(f"Error getting worker {worker_id}: {str(e)}")
            raise
    
    def get_workers_by_category(self, category):
        """
        Obtiene trabajadores por categoría de trabajo
        
        Args:
            category (str): Categoría de trabajo
            
        Returns:
            list: Lista de trabajadores
        """
        try:
            workers = self.firebase.query_data(
                self.WORKERS_PATH,
                order_by='work',
                equal_to=category
            )
            
            if not workers:
                return []
            
            workers_list = []
            for worker_id, worker_data in workers.items():
                worker_data['id'] = worker_id
                workers_list.append(worker_data)
            
            logger.info(f"Retrieved {len(workers_list)} workers in category {category}")
            return workers_list
        except Exception as e:
            logger.error(f"Error getting workers by category: {str(e)}")
            raise
    
    def get_available_workers(self):
        """
        Obtiene trabajadores disponibles
        
        Returns:
            list: Lista de trabajadores disponibles
        """
        try:
            workers = self.firebase.query_data(
                self.WORKERS_PATH,
                order_by='isAvailable',
                equal_to=True
            )
            
            if not workers:
                return []
            
            workers_list = []
            for worker_id, worker_data in workers.items():
                worker_data['id'] = worker_id
                workers_list.append(worker_data)
            
            logger.info(f"Retrieved {len(workers_list)} available workers")
            return workers_list
        except Exception as e:
            logger.error(f"Error getting available workers: {str(e)}")
            raise
    
    def get_online_workers(self):
        """
        Obtiene trabajadores en línea
        
        Returns:
            list: Lista de trabajadores en línea
        """
        try:
            workers = self.firebase.query_data(
                self.WORKERS_PATH,
                order_by='isOnline',
                equal_to=True
            )
            
            if not workers:
                return []
            
            workers_list = []
            for worker_id, worker_data in workers.items():
                worker_data['id'] = worker_id
                workers_list.append(worker_data)
            
            logger.info(f"Retrieved {len(workers_list)} online workers")
            return workers_list
        except Exception as e:
            logger.error(f"Error getting online workers: {str(e)}")
            raise
    
    def create_worker(self, worker_data):
        """
        Crea un nuevo trabajador
        
        Args:
            worker_data (dict): Datos del trabajador
            
        Returns:
            dict: Trabajador creado
        """
        try:
            worker_id = worker_data.get('id')
            
            if not worker_id:
                raise ValueError("Worker ID is required")
            
            # Agregar timestamp
            worker_data['timestamp'] = int(datetime.now().timestamp() * 1000)
            worker_data['isAvailable'] = worker_data.get('isAvailable', True)
            worker_data['isOnline'] = worker_data.get('isOnline', False)
            worker_data['rating'] = worker_data.get('rating', 0)
            worker_data['totalRatings'] = worker_data.get('totalRatings', 0)
            
            path = f"{self.WORKERS_PATH}/{worker_id}"
            self.firebase.set_data(path, worker_data)
            
            logger.info(f"Worker {worker_id} created successfully")
            return worker_data
        except Exception as e:
            logger.error(f"Error creating worker: {str(e)}")
            raise
    
    def update_worker(self, worker_id, update_data):
        """
        Actualiza datos de un trabajador
        
        Args:
            worker_id (str): ID del trabajador
            update_data (dict): Datos a actualizar
            
        Returns:
            bool: True si fue exitoso
        """
        try:
            # Actualizar timestamp
            update_data['timestamp'] = int(datetime.now().timestamp() * 1000)
            
            path = f"{self.WORKERS_PATH}/{worker_id}"
            self.firebase.update_data(path, update_data)
            
            logger.info(f"Worker {worker_id} updated successfully")
            return True
        except Exception as e:
            logger.error(f"Error updating worker {worker_id}: {str(e)}")
            raise
    
    def update_worker_availability(self, worker_id, is_available):
        """
        Actualiza disponibilidad de un trabajador
        
        Args:
            worker_id (str): ID del trabajador
            is_available (bool): Estado de disponibilidad
            
        Returns:
            bool: True si fue exitoso
        """
        try:
            update_data = {
                'isAvailable': is_available,
                'timestamp': int(datetime.now().timestamp() * 1000)
            }
            
            path = f"{self.WORKERS_PATH}/{worker_id}"
            self.firebase.update_data(path, update_data)
            
            logger.info(f"Worker {worker_id} availability updated to {is_available}")
            return True
        except Exception as e:
            logger.error(f"Error updating worker availability: {str(e)}")
            raise
    
    def update_worker_online_status(self, worker_id, is_online):
        """
        Actualiza estado en línea de un trabajador
        
        Args:
            worker_id (str): ID del trabajador
            is_online (bool): Estado en línea
            
        Returns:
            bool: True si fue exitoso
        """
        try:
            update_data = {
                'isOnline': is_online,
                'timestamp': int(datetime.now().timestamp() * 1000)
            }
            
            path = f"{self.WORKERS_PATH}/{worker_id}"
            self.firebase.update_data(path, update_data)
            
            logger.info(f"Worker {worker_id} online status updated to {is_online}")
            return True
        except Exception as e:
            logger.error(f"Error updating worker online status: {str(e)}")
            raise
    
    def update_worker_location(self, worker_id, latitude, longitude):
        """
        Actualiza ubicación de un trabajador
        
        Args:
            worker_id (str): ID del trabajador
            latitude (float): Latitud
            longitude (float): Longitud
            
        Returns:
            bool: True si fue exitoso
        """
        try:
            update_data = {
                'latitude': latitude,
                'longitude': longitude,
                'timestamp': int(datetime.now().timestamp() * 1000)
            }
            
            path = f"{self.WORKERS_PATH}/{worker_id}"
            self.firebase.update_data(path, update_data)
            
            logger.info(f"Worker {worker_id} location updated")
            return True
        except Exception as e:
            logger.error(f"Error updating worker location: {str(e)}")
            raise
    
    def update_worker_rating(self, worker_id, new_rating):
        """
        Actualiza rating de un trabajador
        
        Args:
            worker_id (str): ID del trabajador
            new_rating (float): Nueva calificación (1-5)
            
        Returns:
            bool: True si fue exitoso
        """
        try:
            # Obtener datos actuales del trabajador
            worker = self.get_worker_by_id(worker_id)
            
            if not worker:
                raise ValueError(f"Worker {worker_id} not found")
            
            current_rating = worker.get('rating', 0)
            total_ratings = worker.get('totalRatings', 0)
            
            # Calcular nuevo rating
            if total_ratings == 0:
                final_rating = new_rating
                new_total = 1
            else:
                total_score = current_rating * total_ratings
                new_total = total_ratings + 1
                final_rating = (total_score + new_rating) / new_total
            
            update_data = {
                'rating': round(final_rating, 2),
                'totalRatings': new_total,
                'timestamp': int(datetime.now().timestamp() * 1000)
            }
            
            path = f"{self.WORKERS_PATH}/{worker_id}"
            self.firebase.update_data(path, update_data)
            
            logger.info(f"Worker {worker_id} rating updated to {final_rating}")
            return True
        except Exception as e:
            logger.error(f"Error updating worker rating: {str(e)}")
            raise
    
    def delete_worker(self, worker_id):
        """
        Elimina un trabajador
        
        Args:
            worker_id (str): ID del trabajador
            
        Returns:
            bool: True si fue exitoso
        """
        try:
            path = f"{self.WORKERS_PATH}/{worker_id}"
            self.firebase.delete_data(path)
            
            logger.info(f"Worker {worker_id} deleted successfully")
            return True
        except Exception as e:
            logger.error(f"Error deleting worker {worker_id}: {str(e)}")
            raise
    
    def worker_exists(self, worker_id):
        """
        Verifica si un trabajador existe
        
        Args:
            worker_id (str): ID del trabajador
            
        Returns:
            bool: True si existe
        """
        try:
            worker = self.get_worker_by_id(worker_id)
            return worker is not None
        except Exception as e:
            logger.error(f"Error checking if worker exists: {str(e)}")
            raise
    
    def count_workers(self):
        """
        Cuenta el total de trabajadores
        
        Returns:
            int: Total de trabajadores
        """
        try:
            workers = self.firebase.get_data(self.WORKERS_PATH)
            count = len(workers) if workers else 0
            
            logger.info(f"Total workers: {count}")
            return count
        except Exception as e:
            logger.error(f"Error counting workers: {str(e)}")
            raise
    
    def count_verified_workers(self):
        """
        Cuenta los trabajadores verificados (con verificationStatus.status == 'approved')
        
        Returns:
            int: Total de trabajadores verificados
        """
        try:
            all_workers = self.get_all_workers()
            
            if not all_workers:
                return 0
            
            verified_count = 0
            for worker in all_workers:
                verification_status = worker.get('verificationStatus', {})
                if isinstance(verification_status, dict):
                    status = verification_status.get('status', '')
                    if status == 'approved':
                        verified_count += 1
            
            logger.info(f"Total verified workers: {verified_count}")
            return verified_count
        except Exception as e:
            logger.error(f"Error counting verified workers: {str(e)}")
            raise
    
    def get_workers_statistics(self):
        """
        Obtiene estadísticas generales de trabajadores
        
        Returns:
            dict: Estadísticas
        """
        try:
            all_workers = self.get_all_workers()
            
            if not all_workers:
                return {
                    'total': 0,
                    'available': 0,
                    'online': 0,
                    'verified': 0,
                    'by_category': {}
                }
            
            stats = {
                'total': len(all_workers),
                'available': 0,
                'online': 0,
                'verified': 0,
                'by_category': {}
            }
            
            for worker in all_workers:
                # Contar disponibles
                if worker.get('isAvailable', False):
                    stats['available'] += 1
                
                # Contar en línea
                if worker.get('isOnline', False):
                    stats['online'] += 1
                
                # Contar verificados
                verification_status = worker.get('verificationStatus', {})
                if isinstance(verification_status, dict):
                    if verification_status.get('status') == 'approved':
                        stats['verified'] += 1
                
                # Contar por categoría
                category = worker.get('work', 'Sin categoría')
                stats['by_category'][category] = stats['by_category'].get(category, 0) + 1
            
            logger.info(f"Worker statistics calculated")
            return stats
        except Exception as e:
            logger.error(f"Error getting worker statistics: {str(e)}")
            raise
    
    def search_workers(self, query):
        """
        Busca trabajadores por nombre, apellido o categoría
        
        Args:
            query (str): Término de búsqueda
            
        Returns:
            list: Lista de trabajadores que coinciden
        """
        try:
            all_workers = self.get_all_workers()
            
            if not all_workers or not query:
                return all_workers
            
            query_lower = query.lower().strip()
            results = []
            
            for worker in all_workers:
                # Buscar en nombre
                if worker.get('name', '').lower().find(query_lower) != -1:
                    results.append(worker)
                    continue
                
                # Buscar en apellido
                if worker.get('lastName', '').lower().find(query_lower) != -1:
                    results.append(worker)
                    continue
                
                # Buscar en email
                if worker.get('email', '').lower().find(query_lower) != -1:
                    results.append(worker)
                    continue
                
                # Buscar en categoría
                if worker.get('work', '').lower().find(query_lower) != -1:
                    results.append(worker)
                    continue
            
            logger.info(f"Search for '{query}' returned {len(results)} results")
            return results
        except Exception as e:
            logger.error(f"Error searching workers: {str(e)}")
            raise


# Instancia global del servicio
worker_service = WorkerService()