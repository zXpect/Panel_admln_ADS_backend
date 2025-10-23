from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    WorkerViewSet,
    DocumentViewSet,
    ClientViewSet,
    DashboardStatsView,
    DashboardWeeklyTrendsView,
    DashboardMonthlyTrendsView,
    DashboardActivityStatsView,
)

# Router para ViewSets
router = DefaultRouter()
router.register(r'workers', WorkerViewSet, basename='worker')
router.register(r'documents', DocumentViewSet, basename='document')
router.register(r'clients', ClientViewSet, basename='client')

urlpatterns = [
    # Dashboard - Estadísticas generales
    path('dashboard/stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
    
    # Dashboard - Tendencias semanales (últimos 7 días)
    path('dashboard/weekly-trends/', DashboardWeeklyTrendsView.as_view(), name='dashboard-weekly-trends'),
    
    # Dashboard - Tendencias mensuales (últimos 30 días)
    path('dashboard/monthly-trends/', DashboardMonthlyTrendsView.as_view(), name='dashboard-monthly-trends'),
    
    # Dashboard - Estadísticas de actividad detalladas (NUEVO)
    path('dashboard/activity-stats/', DashboardActivityStatsView.as_view(), name='dashboard-activity-stats'),
    
    # ViewSets routes
    path('', include(router.urls)),
]

"""
RUTAS DISPONIBLES:

WORKERS:
- GET    /api/workers/                      - Listar trabajadores
- GET    /api/workers/{id}/                 - Detalle de trabajador
- POST   /api/workers/                      - Crear trabajador
- PUT    /api/workers/{id}/                 - Actualizar trabajador completo
- PATCH  /api/workers/{id}/                 - Actualizar campos específicos
- DELETE /api/workers/{id}/                 - Eliminar trabajador
- GET    /api/workers/statistics/           - Estadísticas de trabajadores
- PATCH  /api/workers/{id}/availability/    - Actualizar disponibilidad
- PATCH  /api/workers/{id}/verification_status/ - Actualizar estado de verificación
- PATCH  /api/workers/{id}/online_status/   - Actualizar estado en línea
- PATCH  /api/workers/{id}/location/        - Actualizar ubicación
- POST   /api/workers/{id}/add_rating/      - Agregar calificación

DOCUMENTS:
- GET    /api/documents/pending/                           - Documentos pendientes
- GET    /api/documents/worker/{worker_id}/                - Todos los documentos del trabajador
- GET    /api/documents/worker/{worker_id}/hoja-vida/      - Hoja de vida
- GET    /api/documents/worker/{worker_id}/antecedentes/   - Antecedentes judiciales
- GET    /api/documents/worker/{worker_id}/titulos/        - Títulos
- GET    /api/documents/worker/{worker_id}/cartas/         - Cartas de recomendación
- POST   /api/documents/                                    - Crear documento (CORREGIDO)
- POST   /api/documents/approve/                           - Aprobar documento
- POST   /api/documents/reject/                            - Rechazar documento
- GET    /api/documents/worker/{worker_id}/check-requirements/ - Verificar documentos requeridos
- DELETE /api/documents/delete/                            - Eliminar documento
- GET    /api/documents/file-url/                          - Obtener URL de archivo

CLIENTS:
- GET    /api/clients/        - Listar clientes
- GET    /api/clients/{id}/   - Detalle de cliente
- GET    /api/clients/count/  - Total de clientes

DASHBOARD:
- GET    /api/dashboard/stats/  - Estadísticas generales

AUTH:
- POST   /api/auth/token/         - Obtener token JWT
- POST   /api/auth/token/refresh/ - Refrescar token JWT
"""