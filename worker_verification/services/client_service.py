from .firebase_service import firebase_service
import logging

logger = logging.getLogger(__name__)


class ClientService:
    """
    Servicio para manejar operaciones relacionadas con clientes
    """
    
    CLIENTS_PATH = 'User/Clientes'
    
    def __init__(self):
        self.firebase = firebase_service
    
    def get_all_clients(self):
        """
        Obtiene todos los clientes
        
        Returns:
            list: Lista de clientes
        """
        try:
            clients = self.firebase.get_data(self.CLIENTS_PATH)
            
            if not clients:
                return []
            
            # Convertir a lista
            clients_list = []
            for client_id, client_data in clients.items():
                client_data['id'] = client_id
                clients_list.append(client_data)
            
            logger.info(f"Retrieved {len(clients_list)} clients")
            return clients_list
        except Exception as e:
            logger.error(f"Error getting all clients: {str(e)}")
            raise
    
    def get_client_by_id(self, client_id):
        """
        Obtiene un cliente por su ID
        
        Args:
            client_id (str): ID del cliente
            
        Returns:
            dict: Datos del cliente
        """
        try:
            path = f"{self.CLIENTS_PATH}/{client_id}"
            client = self.firebase.get_data(path)
            
            if client:
                client['id'] = client_id
                logger.info(f"Retrieved client {client_id}")
            else:
                logger.warning(f"Client {client_id} not found")
            
            return client
        except Exception as e:
            logger.error(f"Error getting client {client_id}: {str(e)}")
            raise
    
    def count_clients(self):
        """
        Cuenta el total de clientes
        
        Returns:
            int: Total de clientes
        """
        try:
            clients = self.firebase.get_data(self.CLIENTS_PATH)
            count = len(clients) if clients else 0
            
            logger.info(f"Total clients: {count}")
            return count
        except Exception as e:
            logger.error(f"Error counting clients: {str(e)}")
            raise
    
    def search_clients(self, query):
        """
        Busca clientes por nombre o email
        
        Args:
            query (str): Término de búsqueda
            
        Returns:
            list: Lista de clientes que coinciden
        """
        try:
            all_clients = self.get_all_clients()
            
            if not all_clients or not query:
                return all_clients
            
            query_lower = query.lower().strip()
            results = []
            
            for client in all_clients:
                # Buscar en nombre
                if client.get('name', '').lower().find(query_lower) != -1:
                    results.append(client)
                    continue
                
                # Buscar en apellido
                if client.get('lastName', '').lower().find(query_lower) != -1:
                    results.append(client)
                    continue
                
                # Buscar en email
                if client.get('email', '').lower().find(query_lower) != -1:
                    results.append(client)
                    continue
            
            logger.info(f"Search for '{query}' returned {len(results)} results")
            return results
        except Exception as e:
            logger.error(f"Error searching clients: {str(e)}")
            raise


# Instancia global del servicio
client_service = ClientService()