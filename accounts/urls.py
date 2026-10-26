from django.urls import path

from .views import AdminAccountStatusView, DeletedAccountView, MeView, WorkerStatsView

app_name = 'accounts'

urlpatterns = [
    path('me/', MeView.as_view(), name='me'),
    path('accounts/deleted-status/', DeletedAccountView.as_view(), name='deleted-status'),
    # Antes de las rutas del panel en /api/workers/ (worker_verification)
    path('workers/<str:worker_id>/stats/', WorkerStatsView.as_view(), name='worker-stats'),
    path('admin/accounts/<str:uid>/status/', AdminAccountStatusView.as_view(), name='admin-account-status'),
]

"""
RUTAS DISPONIBLES (montadas en /api/):

- DELETE /api/me/                    - Eliminar la cuenta y los datos personales (app; 409 con un servicio en curso)
- POST   /api/accounts/deleted-status/ - ¿La cuenta de este correo fue eliminada? (app, pública, por IP)
- GET    /api/workers/{id}/stats/      - Trabajos realizados y calificación del trabajador (app)
- PATCH  /api/admin/accounts/{uid}/status/ - Suspender o reactivar una cuenta (panel; queda en la auditoría)
"""
