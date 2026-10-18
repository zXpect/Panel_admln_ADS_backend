from django.urls import path

from .views import (
    AdminAuditLogView,
    AdminCatalogView,
    AdminCategoryDetailView,
    AdminConfigDetailView,
    AdminConfigListView,
    AdminTaskCreateView,
    AdminTaskDetailView,
    CatalogView,
    EstimateView,
)

app_name = 'pricing'

# Montadas en /api/ (ver admin_panel/urls.py), antes de payments.request_urls.
# Las de la app requieren el ID token de Firebase; las de admin/, el JWT del panel.
urlpatterns = [
    path('catalog/', CatalogView.as_view(), name='catalog'),
    path('requests/estimate/', EstimateView.as_view(), name='estimate'),
    path('admin/catalog/', AdminCatalogView.as_view(), name='admin-catalog'),
    path('admin/catalog/categories/<int:pk>/', AdminCategoryDetailView.as_view(), name='admin-category'),
    path('admin/catalog/tasks/', AdminTaskCreateView.as_view(), name='admin-task-create'),
    path('admin/catalog/tasks/<int:pk>/', AdminTaskDetailView.as_view(), name='admin-task'),
    path('admin/config/', AdminConfigListView.as_view(), name='admin-config'),
    path('admin/config/<str:key>/', AdminConfigDetailView.as_view(), name='admin-config-detail'),
    path('admin/audit/', AdminAuditLogView.as_view(), name='admin-audit'),
]

"""
RUTAS DISPONIBLES (app móvil):

- GET    /api/catalog/              - Oficios y tareas activos con el rango de Ubaté
- POST   /api/requests/estimate/    - Precio de referencia de las tareas elegidas (no crea nada)

RUTAS DEL PANEL (JWT; cada cambio queda en ConfigAuditLog):

- GET    /api/admin/catalog/                    - Oficios y tareas, incluidos los inactivos
- PATCH  /api/admin/catalog/categories/{id}/    - Nombre, orden o activar/desactivar un oficio
- POST   /api/admin/catalog/tasks/              - Crear tarea
- PATCH  /api/admin/catalog/tasks/{id}/         - Editar o desactivar tarea
- GET    /api/admin/config/                     - Parámetros de cotización y búsqueda
- PATCH  /api/admin/config/{key}/               - Cambiar un parámetro
- GET    /api/admin/audit/?entity=              - Historial de cambios
"""
