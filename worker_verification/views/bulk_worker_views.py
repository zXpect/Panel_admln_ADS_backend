from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import HttpResponse
from ..services.bulk_worker_service import bulk_worker_service
from ..serializers.bulk_worker_serializers import BulkWorkerResultSerializer
import logging
import io

logger = logging.getLogger(__name__)


class BulkWorkerUploadView(APIView):
    """
    Vista para carga masiva de trabajadores desde Excel
    
    POST /api/workers/bulk-upload/
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request):
        """
        Carga masiva de trabajadores desde archivo Excel
        
        Form data:
        - file: Archivo Excel (.xlsx o .xls)
        
        Retorna:
        - Reporte detallado de éxitos y errores
        - Lista de credenciales generadas
        """
        try:
            # Validar que se envió un archivo
            if 'file' not in request.FILES:
                return Response({
                    'success': False,
                    'error': 'No se proporcionó archivo'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            excel_file = request.FILES['file']
            
            # Validar extensión
            if not excel_file.name.endswith(('.xlsx', '.xls')):
                return Response({
                    'success': False,
                    'error': 'El archivo debe ser un Excel (.xlsx o .xls)'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validar tamaño (máximo 10MB)
            if excel_file.size > 10 * 1024 * 1024:
                return Response({
                    'success': False,
                    'error': 'El archivo es demasiado grande (máximo 10MB)'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Procesar archivo
            logger.info(f"Processing bulk upload: {excel_file.name}")
            results = bulk_worker_service.process_excel_file(excel_file)
            
            # Serializar resultados
            serializer = BulkWorkerResultSerializer(results)
            
            # Determinar código de respuesta
            if results['failed'] == 0:
                response_status = status.HTTP_201_CREATED
            elif results['successful'] == 0:
                response_status = status.HTTP_400_BAD_REQUEST
            else:
                response_status = status.HTTP_207_MULTI_STATUS
            
            return Response({
                'success': results['successful'] > 0,
                'message': f"Procesados: {results['total_processed']}, Exitosos: {results['successful']}, Fallidos: {results['failed']}",
                'data': serializer.data
            }, status=response_status)
            
        except ValueError as e:
            logger.error(f"Validation error in bulk upload: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Error in bulk upload: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Error procesando archivo',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BulkWorkerTemplateView(APIView):
    """
    Vista para descargar template de Excel
    
    GET /api/workers/bulk-upload-template/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        Descarga un template de Excel con ejemplos
        """
        try:
            # Generar template
            df = bulk_worker_service.generate_excel_template()
            
            # Crear archivo Excel en memoria
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Trabajadores')
                
                # Ajustar ancho de columnas
                worksheet = writer.sheets['Trabajadores']
                for idx, col in enumerate(df.columns):
                    max_length = max(
                        df[col].astype(str).apply(len).max(),
                        len(col)
                    ) + 2
                    worksheet.column_dimensions[chr(65 + idx)].width = max_length
            
            output.seek(0)
            
            # Preparar respuesta
            response = HttpResponse(
                output.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = 'attachment; filename=template_trabajadores.xlsx'
            
            logger.info("Template downloaded")
            return response
            
        except Exception as e:
            logger.error(f"Error generating template: {str(e)}")
            return Response({
                'success': False,
                'error': 'Error generando template',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


import pandas as pd