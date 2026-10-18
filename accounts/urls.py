from django.urls import path

from .views import MeView

app_name = 'accounts'

urlpatterns = [
    path('me/', MeView.as_view(), name='me'),
]

"""
RUTAS DISPONIBLES (montadas en /api/):

- DELETE /api/me/   - Eliminar la cuenta y los datos personales (app; 409 con un servicio en curso)
"""
