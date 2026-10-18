from django.urls import path

from .views import MeView, WorkerStatsView

app_name = 'accounts'

urlpatterns = [
    path('me/', MeView.as_view(), name='me'),
    # Antes de las rutas del panel en /api/workers/ (worker_verification)
    path('workers/<str:worker_id>/stats/', WorkerStatsView.as_view(), name='worker-stats'),
]

"""
RUTAS DISPONIBLES (montadas en /api/):

- DELETE /api/me/                    - Eliminar la cuenta y los datos personales (app; 409 con un servicio en curso)
- GET    /api/workers/{id}/stats/      - Trabajos realizados y calificación del trabajador (app)
"""
