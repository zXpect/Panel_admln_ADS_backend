from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from ..services.document_service import document_service
from ..serializers import (
    DocumentSerializer,
    DocumentApprovalSerializer,
    DocumentRejectionSerializer,
    DocumentRequirementCheckSerializer,
    DocumentListSerializer,
)
import logging

logger = logging.getLogger(__name__)


class DocumentViewSet(viewsets.ViewSet):
    """
    ViewSet para operaciones con documentos de trabajadores
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        """
        GET /api/documents/pending/
        Obtiene todos los documentos pendientes de revisión
        """
        try:
            pending_docs = document_service.get_pending_documents()
            serializer = DocumentListSerializer(pending_docs, many=True)
            
            return Response({
                'success': True,
                'count': len(pending_docs),
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting pending documents: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'], url_path='worker/(?P<worker_id>[^/.]+)')
    def worker_documents(self, request, worker_id=None):
        """
        GET /api/documents/worker/{worker_id}/
        Obtiene todos los documentos de un trabajador
        """
        try:
            documents = document_service.get_all_worker_documents(worker_id)
            
            return Response({
                'success': True,
                'data': documents
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting worker documents: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'], url_path='worker/(?P<worker_id>[^/.]+)/hoja-vida')
    def hoja_vida(self, request, worker_id=None):
        """
        GET /api/documents/worker/{worker_id}/hoja-vida/
        Obtiene la hoja de vida de un trabajador
        """
        try:
            hoja_vida = document_service.get_hoja_vida(worker_id)
            
            if not hoja_vida:
                return Response({
                    'success': False,
                    'error': 'Hoja de vida no encontrada'
                }, status=status.HTTP_404_NOT_FOUND)
            
            return Response({
                'success': True,
                'data': hoja_vida
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting hoja de vida: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'], url_path='worker/(?P<worker_id>[^/.]+)/antecedentes')
    def antecedentes(self, request, worker_id=None):
        """
        GET /api/documents/worker/{worker_id}/antecedentes/
        Obtiene los antecedentes judiciales de un trabajador
        """
        try:
            antecedentes = document_service.get_antecedentes(worker_id)
            
            if not antecedentes:
                return Response({
                    'success': False,
                    'error': 'Antecedentes no encontrados'
                }, status=status.HTTP_404_NOT_FOUND)
            
            return Response({
                'success': True,
                'data': antecedentes
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting antecedentes: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'], url_path='worker/(?P<worker_id>[^/.]+)/titulos')
    def titulos(self, request, worker_id=None):
        """
        GET /api/documents/worker/{worker_id}/titulos/
        Obtiene todos los títulos de un trabajador
        """
        try:
            titulos = document_service.get_titulos(worker_id)
            
            return Response({
                'success': True,
                'data': titulos
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting titulos: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'], url_path='worker/(?P<worker_id>[^/.]+)/cartas')
    def cartas(self, request, worker_id=None):
        """
        GET /api/documents/worker/{worker_id}/cartas/
        Obtiene todas las cartas de recomendación de un trabajador
        """
        try:
            cartas = document_service.get_cartas_recomendacion(worker_id)
            
            return Response({
                'success': True,
                'data': cartas
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting cartas: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def create(self, request):
        """
        POST /api/documents/
        Crea un nuevo documento
        
        Body ejemplo:
        {
            "id": "doc123",
            "workerId": "worker123",
            "documentType": "hoja_de_vida",
            "category": "hojaDeVida",
            "fileName": "cv.pdf",
            "fileUrl": "https://...",
            "fileType": "application/pdf",
            "fileSize": 204800
        }
        """
        try:
            serializer = DocumentSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            worker_id = serializer.validated_data['workerId']
            document = document_service.create_document(worker_id, serializer.validated_data)
            
            return Response({
                'success': True,
                'message': 'Documento creado exitosamente',
                'data': document
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error creating document: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'], url_path='approve')
    def approve_document(self, request):
        """
        POST /api/documents/approve/
        Aprueba un documento
        
        Body:
        {
            "workerId": "worker123",
            "category": "hojaDeVida",
            "subcategory": null,
            "documentId": "doc123",
            "reviewerId": "admin123"
        }
        """
        try:
            # Validar datos básicos
            worker_id = request.data.get('workerId')
            category = request.data.get('category')
            subcategory = request.data.get('subcategory')
            document_id = request.data.get('documentId')
            
            # Validar reviewerId
            serializer = DocumentApprovalSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            reviewer_id = serializer.validated_data['reviewerId']
            
            if not all([worker_id, category, document_id]):
                return Response({
                    'success': False,
                    'error': 'Faltan campos requeridos: workerId, category, documentId'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            document_service.approve_document(
                worker_id,
                category,
                subcategory,
                document_id,
                reviewer_id
            )
            
            return Response({
                'success': True,
                'message': 'Documento aprobado exitosamente'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error approving document: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'], url_path='reject')
    def reject_document(self, request):
        """
        POST /api/documents/reject/
        Rechaza un documento
        
        Body:
        {
            "workerId": "worker123",
            "category": "hojaDeVida",
            "subcategory": null,
            "documentId": "doc123",
            "reviewerId": "admin123",
            "reason": "El documento no es legible"
        }
        """
        try:
            # Validar datos básicos
            worker_id = request.data.get('workerId')
            category = request.data.get('category')
            subcategory = request.data.get('subcategory')
            document_id = request.data.get('documentId')
            
            # Validar reviewerId y reason
            serializer = DocumentRejectionSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            reviewer_id = serializer.validated_data['reviewerId']
            reason = serializer.validated_data['reason']
            
            if not all([worker_id, category, document_id]):
                return Response({
                    'success': False,
                    'error': 'Faltan campos requeridos: workerId, category, documentId'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            document_service.reject_document(
                worker_id,
                category,
                subcategory,
                document_id,
                reviewer_id,
                reason
            )
            
            return Response({
                'success': True,
                'message': 'Documento rechazado exitosamente'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error rejecting document: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'], url_path='worker/(?P<worker_id>[^/.]+)/check-requirements')
    def check_requirements(self, request, worker_id=None):
        """
        GET /api/documents/worker/{worker_id}/check-requirements/
        Verifica si un trabajador tiene todos los documentos requeridos
        """
        try:
            requirements = document_service.has_all_required_documents(worker_id)
            serializer = DocumentRequirementCheckSerializer(requirements)
            
            return Response({
                'success': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error checking requirements: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['delete'], url_path='delete')
    def delete_document(self, request):
        """
        DELETE /api/documents/delete/
        Elimina un documento
        
        Body:
        {
            "workerId": "worker123",
            "category": "hojaDeVida",
            "subcategory": null,
            "documentId": "doc123"
        }
        """
        try:
            worker_id = request.data.get('workerId')
            category = request.data.get('category')
            subcategory = request.data.get('subcategory')
            document_id = request.data.get('documentId')
            
            if not all([worker_id, category, document_id]):
                return Response({
                    'success': False,
                    'error': 'Faltan campos requeridos: workerId, category, documentId'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            document_service.delete_document(
                worker_id,
                category,
                subcategory,
                document_id
            )
            
            return Response({
                'success': True,
                'message': 'Documento eliminado exitosamente'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error deleting document: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'], url_path='file-url')
    def get_file_url(self, request):
        """
        GET /api/documents/file-url/?workerId=xxx&category=xxx&subcategory=xxx&filename=xxx
        Obtiene la URL temporal de un archivo en Storage
        """
        try:
            worker_id = request.query_params.get('workerId')
            category = request.query_params.get('category')
            subcategory = request.query_params.get('subcategory')
            filename = request.query_params.get('filename')
            
            if not all([worker_id, category, filename]):
                return Response({
                    'success': False,
                    'error': 'Faltan parámetros requeridos: workerId, category, filename'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            url = document_service.get_file_url(
                worker_id,
                category,
                subcategory,
                filename
            )
            
            return Response({
                'success': True,
                'url': url
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting file URL: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)