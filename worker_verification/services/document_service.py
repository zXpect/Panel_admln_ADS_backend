from .firebase_service import firebase_service
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class DocumentService:
    """
    Servicio para manejar operaciones relacionadas con documentos de trabajadores
    """
    
    DOCUMENTS_PATH = 'WorkerDocuments'
    STORAGE_PATH = 'worker_documents'
    
    # Tipos de documentos
    TYPE_HOJA_VIDA = 'hoja_de_vida'
    TYPE_ANTECEDENTES = 'antecedentes_judiciales'
    TYPE_TITULO = 'titulo'
    TYPE_CARTA_RECOMENDACION = 'carta_recomendacion'
    
    # Estados
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    
    # Categorías
    CATEGORY_HOJA_VIDA = 'hojaDeVida'
    CATEGORY_ANTECEDENTES = 'antecedentesJudiciales'
    CATEGORY_CERTIFICACIONES = 'certificaciones'
    SUBCATEGORY_TITULOS = 'titulos'
    SUBCATEGORY_CARTAS = 'cartasRecomendacion'
    
    def __init__(self):
        self.firebase = firebase_service
    
    def get_all_worker_documents(self, worker_id):
        """
        Obtiene todos los documentos de un trabajador
        
        Args:
            worker_id (str): ID del trabajador
            
        Returns:
            dict: Todos los documentos del trabajador
        """
        try:
            path = f"{self.DOCUMENTS_PATH}/{worker_id}"
            documents = self.firebase.get_data(path)
            
            if not documents:
                logger.info(f"No documents found for worker {worker_id}")
                return {}
            
            logger.info(f"Retrieved documents for worker {worker_id}")
            return documents
        except Exception as e:
            logger.error(f"Error getting worker documents: {str(e)}")
            raise
    
    def get_hoja_vida(self, worker_id):
        """
        Obtiene la hoja de vida de un trabajador
        
        Args:
            worker_id (str): ID del trabajador
            
        Returns:
            dict: Datos de la hoja de vida
        """
        try:
            path = f"{self.DOCUMENTS_PATH}/{worker_id}/{self.CATEGORY_HOJA_VIDA}"
            hoja_vida = self.firebase.get_data(path)
            
            if hoja_vida:
                logger.info(f"Retrieved hoja de vida for worker {worker_id}")
            else:
                logger.info(f"No hoja de vida found for worker {worker_id}")
            
            return hoja_vida
        except Exception as e:
            logger.error(f"Error getting hoja de vida: {str(e)}")
            raise
    
    def get_antecedentes(self, worker_id):
        """
        Obtiene los antecedentes judiciales de un trabajador
        
        Args:
            worker_id (str): ID del trabajador
            
        Returns:
            dict: Datos de antecedentes
        """
        try:
            path = f"{self.DOCUMENTS_PATH}/{worker_id}/{self.CATEGORY_ANTECEDENTES}"
            antecedentes = self.firebase.get_data(path)
            
            if antecedentes:
                logger.info(f"Retrieved antecedentes for worker {worker_id}")
            else:
                logger.info(f"No antecedentes found for worker {worker_id}")
            
            return antecedentes
        except Exception as e:
            logger.error(f"Error getting antecedentes: {str(e)}")
            raise
    
    def get_titulos(self, worker_id):
        """
        Obtiene todos los títulos de un trabajador
        
        Args:
            worker_id (str): ID del trabajador
            
        Returns:
            dict: Títulos del trabajador
        """
        try:
            path = f"{self.DOCUMENTS_PATH}/{worker_id}/{self.CATEGORY_CERTIFICACIONES}/{self.SUBCATEGORY_TITULOS}"
            titulos = self.firebase.get_data(path)
            
            if not titulos:
                logger.info(f"No titulos found for worker {worker_id}")
                return {}
            
            logger.info(f"Retrieved titulos for worker {worker_id}")
            return titulos
        except Exception as e:
            logger.error(f"Error getting titulos: {str(e)}")
            raise
    
    def get_cartas_recomendacion(self, worker_id):
        """
        Obtiene todas las cartas de recomendación de un trabajador
        
        Args:
            worker_id (str): ID del trabajador
            
        Returns:
            dict: Cartas de recomendación
        """
        try:
            path = f"{self.DOCUMENTS_PATH}/{worker_id}/{self.CATEGORY_CERTIFICACIONES}/{self.SUBCATEGORY_CARTAS}"
            cartas = self.firebase.get_data(path)
            
            if not cartas:
                logger.info(f"No cartas found for worker {worker_id}")
                return {}
            
            logger.info(f"Retrieved cartas for worker {worker_id}")
            return cartas
        except Exception as e:
            logger.error(f"Error getting cartas: {str(e)}")
            raise
    
    def create_document(self, worker_id, document_data):
        """
        Crea un nuevo documento
        
        Args:
            worker_id (str): ID del trabajador
            document_data (dict): Datos del documento
            
        Returns:
            dict: Documento creado
        """
        try:
            category = document_data.get('category')
            subcategory = document_data.get('subcategory')
            document_id = document_data.get('id')
            
            if not all([category, document_id]):
                raise ValueError("Missing required fields: category, id")
            
            # Agregar timestamps
            document_data['uploadedAt'] = int(datetime.now().timestamp() * 1000)
            document_data['status'] = self.STATUS_PENDING
            document_data['reviewedAt'] = 0
            document_data['workerId'] = worker_id
            
            # Construir ruta según el tipo de documento
            if category == self.CATEGORY_CERTIFICACIONES and subcategory:
                path = f"{self.DOCUMENTS_PATH}/{worker_id}/{category}/{subcategory}/{document_id}"
            else:
                # Para hoja de vida y antecedentes (nodos únicos)
                path = f"{self.DOCUMENTS_PATH}/{worker_id}/{category}"
                # Usar el documento completo como valor
                document_data['id'] = document_id
            
            self.firebase.set_data(path, document_data)
            
            logger.info(f"Document created for worker {worker_id}")
            return document_data
        except Exception as e:
            logger.error(f"Error creating document: {str(e)}")
            raise
    
    def update_document_status(self, worker_id, category, subcategory, document_id, status):
        """
        Actualiza el estado de un documento
        
        Args:
            worker_id (str): ID del trabajador
            category (str): Categoría del documento
            subcategory (str): Subcategoría (puede ser None)
            document_id (str): ID del documento
            status (str): Nuevo estado
            
        Returns:
            bool: True si fue exitoso
        """
        try:
            update_data = {
                'status': status,
                'reviewedAt': int(datetime.now().timestamp() * 1000)
            }
            
            # Construir ruta
            if subcategory:
                path = f"{self.DOCUMENTS_PATH}/{worker_id}/{category}/{subcategory}/{document_id}"
            else:
                path = f"{self.DOCUMENTS_PATH}/{worker_id}/{category}"
            
            self.firebase.update_data(path, update_data)
            
            logger.info(f"Document status updated to {status} for worker {worker_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating document status: {str(e)}")
            raise
    
    def approve_document(self, worker_id, category, subcategory, document_id, reviewer_id):
        """
        Aprueba un documento
        
        Args:
            worker_id (str): ID del trabajador
            category (str): Categoría del documento
            subcategory (str): Subcategoría (puede ser None)
            document_id (str): ID del documento
            reviewer_id (str): ID del revisor
            
        Returns:
            bool: True si fue exitoso
        """
        try:
            update_data = {
                'status': self.STATUS_APPROVED,
                'reviewedAt': int(datetime.now().timestamp() * 1000),
                'reviewedBy': reviewer_id,
                'rejectionReason': None
            }
            
            # Construir ruta
            if subcategory:
                path = f"{self.DOCUMENTS_PATH}/{worker_id}/{category}/{subcategory}/{document_id}"
            else:
                path = f"{self.DOCUMENTS_PATH}/{worker_id}/{category}"
            
            self.firebase.update_data(path, update_data)
            
            logger.info(f"Document approved for worker {worker_id} by {reviewer_id}")
            return True
        except Exception as e:
            logger.error(f"Error approving document: {str(e)}")
            raise
    
    def reject_document(self, worker_id, category, subcategory, document_id, reviewer_id, reason):
        """
        Rechaza un documento
        
        Args:
            worker_id (str): ID del trabajador
            category (str): Categoría del documento
            subcategory (str): Subcategoría (puede ser None)
            document_id (str): ID del documento
            reviewer_id (str): ID del revisor
            reason (str): Razón del rechazo
            
        Returns:
            bool: True si fue exitoso
        """
        try:
            update_data = {
                'status': self.STATUS_REJECTED,
                'reviewedAt': int(datetime.now().timestamp() * 1000),
                'reviewedBy': reviewer_id,
                'rejectionReason': reason
            }
            
            # Construir ruta
            if subcategory:
                path = f"{self.DOCUMENTS_PATH}/{worker_id}/{category}/{subcategory}/{document_id}"
            else:
                path = f"{self.DOCUMENTS_PATH}/{worker_id}/{category}"
            
            self.firebase.update_data(path, update_data)
            
            logger.info(f"Document rejected for worker {worker_id} by {reviewer_id}")
            return True
        except Exception as e:
            logger.error(f"Error rejecting document: {str(e)}")
            raise
    
    def get_pending_documents(self):
        """
        Obtiene todos los documentos pendientes de revisión
        
        Returns:
            list: Lista de documentos pendientes
        """
        try:
            all_docs = self.firebase.get_data(self.DOCUMENTS_PATH)
            
            if not all_docs:
                return []
            
            pending_docs = []
            
            # Iterar por cada trabajador
            for worker_id, worker_docs in all_docs.items():
                # Revisar hoja de vida
                if self.CATEGORY_HOJA_VIDA in worker_docs:
                    hoja_vida = worker_docs[self.CATEGORY_HOJA_VIDA]
                    if isinstance(hoja_vida, dict) and hoja_vida.get('status') == self.STATUS_PENDING:
                        hoja_vida['workerId'] = worker_id
                        hoja_vida['category'] = self.CATEGORY_HOJA_VIDA
                        pending_docs.append(hoja_vida)
                
                # Revisar antecedentes
                if self.CATEGORY_ANTECEDENTES in worker_docs:
                    antecedentes = worker_docs[self.CATEGORY_ANTECEDENTES]
                    if isinstance(antecedentes, dict) and antecedentes.get('status') == self.STATUS_PENDING:
                        antecedentes['workerId'] = worker_id
                        antecedentes['category'] = self.CATEGORY_ANTECEDENTES
                        pending_docs.append(antecedentes)
                
                # Revisar certificaciones
                if self.CATEGORY_CERTIFICACIONES in worker_docs:
                    certificaciones = worker_docs[self.CATEGORY_CERTIFICACIONES]
                    
                    # Revisar títulos
                    if self.SUBCATEGORY_TITULOS in certificaciones:
                        titulos = certificaciones[self.SUBCATEGORY_TITULOS]
                        if isinstance(titulos, dict):
                            for titulo_id, titulo in titulos.items():
                                if isinstance(titulo, dict) and titulo.get('status') == self.STATUS_PENDING:
                                    titulo['workerId'] = worker_id
                                    titulo['category'] = self.CATEGORY_CERTIFICACIONES
                                    titulo['subcategory'] = self.SUBCATEGORY_TITULOS
                                    titulo['id'] = titulo_id
                                    pending_docs.append(titulo)
                    
                    # Revisar cartas
                    if self.SUBCATEGORY_CARTAS in certificaciones:
                        cartas = certificaciones[self.SUBCATEGORY_CARTAS]
                        if isinstance(cartas, dict):
                            for carta_id, carta in cartas.items():
                                if isinstance(carta, dict) and carta.get('status') == self.STATUS_PENDING:
                                    carta['workerId'] = worker_id
                                    carta['category'] = self.CATEGORY_CERTIFICACIONES
                                    carta['subcategory'] = self.SUBCATEGORY_CARTAS
                                    carta['id'] = carta_id
                                    pending_docs.append(carta)
            
            logger.info(f"Found {len(pending_docs)} pending documents")
            return pending_docs
        except Exception as e:
            logger.error(f"Error getting pending documents: {str(e)}")
            raise
    
    def has_all_required_documents(self, worker_id):
        """
        Verifica si un trabajador tiene todos los documentos obligatorios
    
    Args:
        worker_id (str): ID del trabajador
        
    Returns:
        dict: Estado de documentos requeridos
    """
        try:
            documents = self.get_all_worker_documents(worker_id)
        
            result = {
            'hasHojaVida': False,
            'hasAntecedentes': False,
            'hasTitulo': False,
            'cartasCount': 0,
            'hasMinimumCartas': False,
            'isComplete': False
        }
        
            if not documents:
                return result
        
            # Verificar hoja de vida
            if self.CATEGORY_HOJA_VIDA in documents:
                result['hasHojaVida'] = True
        
            # Verificar antecedentes
            if self.CATEGORY_ANTECEDENTES in documents:
                result['hasAntecedentes'] = True
        
            # Verificar certificaciones (títulos y cartas)
            if self.CATEGORY_CERTIFICACIONES in documents:
                certificaciones = documents[self.CATEGORY_CERTIFICACIONES]
            
                # Títulos
                if self.SUBCATEGORY_TITULOS in certificaciones:
                    titulos = certificaciones[self.SUBCATEGORY_TITULOS]
                    if isinstance(titulos, dict) and len(titulos) > 0:
                        result['hasTitulo'] = True
            
                #  Cartas de recomendación
                if self.SUBCATEGORY_CARTAS in certificaciones:
                    cartas = certificaciones[self.SUBCATEGORY_CARTAS]
                    if isinstance(cartas, dict):
                        result['cartasCount'] = len(cartas)
        
            # Verificar mínimo de cartas (3)
            result['hasMinimumCartas'] = result['cartasCount'] >= 3
        
            # Verificar si está completo (incluye título ahora 🔥)
            result['isComplete'] = (
                result['hasHojaVida'] and 
                result['hasAntecedentes'] and 
                result['hasTitulo'] and
                result['hasMinimumCartas']
            )
        
            logger.info(f"Document verification for worker {worker_id}: {result}")
            return result
        except Exception as e:
            logger.error(f"Error checking required documents: {str(e)}")
            raise
    
    def delete_document(self, worker_id, category, subcategory, document_id):
        """
        Elimina un documento
        
        Args:
            worker_id (str): ID del trabajador
            category (str): Categoría del documento
            subcategory (str): Subcategoría (puede ser None)
            document_id (str): ID del documento
            
        Returns:
            bool: True si fue exitoso
        """
        try:
            # Construir ruta
            if subcategory:
                path = f"{self.DOCUMENTS_PATH}/{worker_id}/{category}/{subcategory}/{document_id}"
            else:
                path = f"{self.DOCUMENTS_PATH}/{worker_id}/{category}"
            
            self.firebase.delete_data(path)
            
            logger.info(f"Document deleted for worker {worker_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting document: {str(e)}")
            raise
    
    def get_file_url(self, worker_id, category, subcategory, filename):
        """
        Obtiene la URL de un archivo en Storage
        
        Args:
            worker_id (str): ID del trabajador
            category (str): Categoría
            subcategory (str): Subcategoría (puede ser None)
            filename (str): Nombre del archivo
            
        Returns:
            str: URL del archivo
        """
        try:
            if subcategory:
                storage_path = f"{self.STORAGE_PATH}/{worker_id}/{category}/{subcategory}/{filename}"
            else:
                storage_path = f"{self.STORAGE_PATH}/{worker_id}/{category}/{filename}"
            
            url = self.firebase.get_file_url(storage_path)
            
            logger.info(f"File URL obtained for {storage_path}")
            return url
        except Exception as e:
            logger.error(f"Error getting file URL: {str(e)}")
            raise


# Instancia global del servicio
document_service = DocumentService()