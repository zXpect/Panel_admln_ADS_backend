from django.urls import path

from .views import (
    NotificationView,
    QuoteAcceptView,
    QuoteLimitsView,
    QuoteRejectView,
    QuoteSubmitView,
    RatingView,
)

app_name = 'service_requests'

# Montadas en /api/ (ver admin_panel/urls.py). Todas requieren el ID token de Firebase.
urlpatterns = [
    path('requests/quote-limits/', QuoteLimitsView.as_view(), name='quote-limits'),
    path('requests/<str:request_id>/quote/', QuoteSubmitView.as_view(), name='quote-submit'),
    path('requests/<str:request_id>/quote/accept/', QuoteAcceptView.as_view(), name='quote-accept'),
    path('requests/<str:request_id>/quote/reject/', QuoteRejectView.as_view(), name='quote-reject'),
    path('requests/<str:request_id>/rating/', RatingView.as_view(), name='rating'),
    path('notifications/', NotificationView.as_view(), name='notifications'),
]

"""
RUTAS DISPONIBLES (app móvil):

SERVICE REQUESTS:
- GET    /api/requests/quote-limits/?service_type=X   - Rango de precio permitido
- POST   /api/requests/{id}/quote/                    - Enviar cotización (trabajador)
- POST   /api/requests/{id}/quote/accept/             - Aceptar cotización (cliente)
- POST   /api/requests/{id}/quote/reject/             - Rechazar cotización (cliente)
- POST   /api/requests/{id}/rating/                   - Calificar servicio pagado (cliente)

NOTIFICATIONS:
- POST   /api/notifications/                          - Notificar al otro participante (FCM desde el backend)
"""
