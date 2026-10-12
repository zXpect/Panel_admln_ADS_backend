from django.urls import path

from .views import (
    CancelView,
    NotificationView,
    QuoteAcceptView,
    QuoteLimitsView,
    QuoteRejectView,
    QuoteSubmitView,
    RatingView,
    ScheduleView,
    ServiceRequestCreateView,
)

app_name = 'service_requests'

# Montadas en /api/ (ver admin_panel/urls.py). Todas requieren el ID token de Firebase.
urlpatterns = [
    path('requests/', ServiceRequestCreateView.as_view(), name='request-create'),
    path('requests/quote-limits/', QuoteLimitsView.as_view(), name='quote-limits'),
    path('requests/<str:request_id>/quote/', QuoteSubmitView.as_view(), name='quote-submit'),
    path('requests/<str:request_id>/quote/accept/', QuoteAcceptView.as_view(), name='quote-accept'),
    path('requests/<str:request_id>/quote/reject/', QuoteRejectView.as_view(), name='quote-reject'),
    path('requests/<str:request_id>/schedule/', ScheduleView.as_view(), name='schedule'),
    path('requests/<str:request_id>/cancel/', CancelView.as_view(), name='cancel'),
    path('requests/<str:request_id>/rating/', RatingView.as_view(), name='rating'),
    path('notifications/', NotificationView.as_view(), name='notifications'),
]

"""
RUTAS DISPONIBLES (app móvil):

SERVICE REQUESTS:
- POST   /api/requests/                               - Crear solicitud (cliente; congela la referencia y notifica)
- GET    /api/requests/quote-limits/                  - Tarifa mínima y tope (app anterior)
- POST   /api/requests/{id}/quote/                    - Cotizar con motivo y agenda (trabajador)
- POST   /api/requests/{id}/quote/accept/             - Aceptar cotización (cliente)
- POST   /api/requests/{id}/quote/reject/             - Rechazar cotización (cliente)
- POST   /api/requests/{id}/schedule/                 - Reprogramar (trabajador; avisa al cliente)
- POST   /api/requests/{id}/cancel/                   - Cancelar con motivo (cliente o trabajador)
- POST   /api/requests/{id}/rating/                   - Calificar servicio pagado (cliente)

NOTIFICATIONS:
- POST   /api/notifications/                          - Notificar al otro participante (FCM desde el backend)
"""
