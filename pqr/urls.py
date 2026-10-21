from django.urls import path

from .views import PqrDetailView, PqrListCreateView

app_name = 'pqr'

urlpatterns = [
    path('', PqrListCreateView.as_view(), name='pqr-list'),
    path('<int:pk>/', PqrDetailView.as_view(), name='pqr-detail'),
]

"""
RUTAS DISPONIBLES (montadas en /api/pqr/):

- POST   /api/pqr/          - Registrar PQR (app: cliente o trabajador de la solicitud)
- GET    /api/pqr/          - App: las propias. Panel: todas (?status=abierta|en_tramite|cerrada)
- GET    /api/pqr/{id}/     - Detalle (app: solo el autor)
- PATCH  /api/pqr/{id}/     - Pasar a trámite o cerrar con respuesta (panel; avisa al autor)
"""
