import firebase_admin
from firebase_admin import credentials, db, storage
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class FirebaseService:
    """
    Servicio base para interactuar con Firebase
    Implementa Singleton para mantener una única instancia
    """
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FirebaseService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not FirebaseService._initialized:
            self.initialize_firebase()
            FirebaseService._initialized = True

    def initialize_firebase(self):
        """
        Inicializa Firebase Admin SDK
        """
        try:
            # Verificar si ya está inicializado
            if not firebase_admin._apps:
                cred_path = settings.FIREBASE_CONFIG['CREDENTIALS_PATH']
                database_url = settings.FIREBASE_CONFIG['DATABASE_URL']
                storage_bucket = settings.FIREBASE_CONFIG['STORAGE_BUCKET']

                cred = credentials.Certificate(cred_path)
                
                firebase_admin.initialize_app(cred, {
                    'databaseURL': database_url,
                    'storageBucket': storage_bucket
                })
                
                logger.info("Firebase initialized successfully")
            else:
                logger.info("Firebase already initialized")
                
        except Exception as e:
            logger.error(f"Error initializing Firebase: {str(e)}")
            raise

    def get_database_reference(self, path=''):
        """
        Obtiene una referencia a la base de datos
        
        Args:
            path (str): Ruta en la base de datos
            
        Returns:
            DatabaseReference: Referencia a la base de datos
        """
        try:
            return db.reference(path)
        except Exception as e:
            logger.error(f"Error getting database reference: {str(e)}")
            raise

    def get_storage_bucket(self):
        """
        Obtiene el bucket de storage
        
        Returns:
            Bucket: Bucket de Firebase Storage
        """
        try:
            return storage.bucket()
        except Exception as e:
            logger.error(f"Error getting storage bucket: {str(e)}")
            raise

    def get_data(self, path):
        """
        Obtiene datos de una ruta específica
        
        Args:
            path (str): Ruta en la base de datos
            
        Returns:
            dict: Datos obtenidos
        """
        try:
            ref = self.get_database_reference(path)
            data = ref.get()
            logger.debug(f"Data retrieved from {path}")
            return data
        except Exception as e:
            logger.error(f"Error getting data from {path}: {str(e)}")
            raise

    def set_data(self, path, data):
        """
        Establece datos en una ruta específica
        
        Args:
            path (str): Ruta en la base de datos
            data (dict): Datos a establecer
            
        Returns:
            bool: True si fue exitoso
        """
        try:
            ref = self.get_database_reference(path)
            ref.set(data)
            logger.info(f"Data set at {path}")
            return True
        except Exception as e:
            logger.error(f"Error setting data at {path}: {str(e)}")
            raise

    def update_data(self, path, data):
        """
        Actualiza datos en una ruta específica
        
        Args:
            path (str): Ruta en la base de datos
            data (dict): Datos a actualizar
            
        Returns:
            bool: True si fue exitoso
        """
        try:
            ref = self.get_database_reference(path)
            ref.update(data)
            logger.info(f"Data updated at {path}")
            return True
        except Exception as e:
            logger.error(f"Error updating data at {path}: {str(e)}")
            raise

    def delete_data(self, path):
        """
        Elimina datos de una ruta específica
        
        Args:
            path (str): Ruta en la base de datos
            
        Returns:
            bool: True si fue exitoso
        """
        try:
            ref = self.get_database_reference(path)
            ref.delete()
            logger.info(f"Data deleted from {path}")
            return True
        except Exception as e:
            logger.error(f"Error deleting data from {path}: {str(e)}")
            raise

    def query_data(self, path, order_by=None, equal_to=None, limit_to_first=None, limit_to_last=None):
        """
        Realiza consultas en la base de datos
        
        Args:
            path (str): Ruta en la base de datos
            order_by (str): Campo por el cual ordenar
            equal_to: Valor a buscar
            limit_to_first (int): Limitar resultados desde el inicio
            limit_to_last (int): Limitar resultados desde el final
            
        Returns:
            dict: Resultados de la consulta
        """
        try:
            ref = self.get_database_reference(path)
            
            if order_by:
                ref = ref.order_by_child(order_by)
                
            if equal_to is not None:
                ref = ref.equal_to(equal_to)
                
            if limit_to_first:
                ref = ref.limit_to_first(limit_to_first)
                
            if limit_to_last:
                ref = ref.limit_to_last(limit_to_last)
            
            results = ref.get()
            logger.debug(f"Query executed on {path}")
            return results
        except Exception as e:
            logger.error(f"Error querying data from {path}: {str(e)}")
            raise

    def upload_file_to_storage(self, local_path, remote_path):
        """
        Sube un archivo a Firebase Storage
        
        Args:
            local_path (str): Ruta local del archivo
            remote_path (str): Ruta remota en Storage
            
        Returns:
            str: URL pública del archivo
        """
        try:
            bucket = self.get_storage_bucket()
            blob = bucket.blob(remote_path)
            blob.upload_from_filename(local_path)
            blob.make_public()
            
            logger.info(f"File uploaded to {remote_path}")
            return blob.public_url
        except Exception as e:
            logger.error(f"Error uploading file: {str(e)}")
            raise

    def delete_file_from_storage(self, remote_path):
        """
        Elimina un archivo de Firebase Storage
        
        Args:
            remote_path (str): Ruta remota en Storage
            
        Returns:
            bool: True si fue exitoso
        """
        try:
            bucket = self.get_storage_bucket()
            blob = bucket.blob(remote_path)
            blob.delete()
            
            logger.info(f"File deleted from {remote_path}")
            return True
        except Exception as e:
            logger.error(f"Error deleting file: {str(e)}")
            raise

    def get_file_url(self, remote_path):
        """
        Obtiene la URL de un archivo en Storage
        
        Args:
            remote_path (str): Ruta remota en Storage
            
        Returns:
            str: URL del archivo
        """
        try:
            bucket = self.get_storage_bucket()
            blob = bucket.blob(remote_path)
            
            # Generar URL firmada válida por 1 hora
            url = blob.generate_signed_url(
                version="v4",
                expiration=3600,  # 1 hora
                method="GET"
            )
            
            return url
        except Exception as e:
            logger.error(f"Error getting file URL: {str(e)}")
            raise

    def list_files_in_folder(self, folder_path):
        """
        Lista archivos en una carpeta de Storage
        
        Args:
            folder_path (str): Ruta de la carpeta
            
        Returns:
            list: Lista de archivos
        """
        try:
            bucket = self.get_storage_bucket()
            blobs = bucket.list_blobs(prefix=folder_path)
            
            files = [blob.name for blob in blobs]
            logger.debug(f"Listed {len(files)} files in {folder_path}")
            return files
        except Exception as e:
            logger.error(f"Error listing files: {str(e)}")
            raise


# Instancia global del servicio
firebase_service = FirebaseService()