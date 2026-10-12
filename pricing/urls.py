from django.urls import path

from .views import CatalogView, EstimateView

app_name = 'pricing'

# Montadas en /api/ (ver admin_panel/urls.py), antes de payments.request_urls.
# Requieren el ID token de Firebase.
urlpatterns = [
    path('catalog/', CatalogView.as_view(), name='catalog'),
    path('requests/estimate/', EstimateView.as_view(), name='estimate'),
]

"""
RUTAS DISPONIBLES (app móvil):

- GET    /api/catalog/              - Oficios y tareas activos con el rango de Ubaté
- POST   /api/requests/estimate/    - Precio de referencia de las tareas elegidas (no crea nada)
"""
