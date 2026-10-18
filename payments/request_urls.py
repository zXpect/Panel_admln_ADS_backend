from django.urls import path

from .views import (
    CancelView,
    CashReceivedView,
    NotificationView,
    PaymentMethodView,
    QuoteAcceptView,
    QuoteLimitsView,
    QuoteRejectView,
    QuoteSubmitView,
    RatingView,
    RequoteAnswerView,
    RequoteView,
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
    path('requests/<str:request_id>/requote/', RequoteView.as_view(), name='requote'),
    path('requests/<str:request_id>/requote/accept/', RequoteAnswerView.as_view(accept=True), name='requote-accept'),
    path('requests/<str:request_id>/requote/reject/', RequoteAnswerView.as_view(accept=False), name='requote-reject'),
    path('requests/<str:request_id>/payment-method/', PaymentMethodView.as_view(), name='payment-method'),
    path('requests/<str:request_id>/cash-received/', CashReceivedView.as_view(), name='cash-received'),
    path('requests/<str:request_id>/rating/', RatingView.as_view(), name='rating'),
    path('notifications/', NotificationView.as_view(), name='notifications'),
]

"""
RUTAS DISPONIBLES (app móvil):

SERVICE REQUESTS:
- POST   /api/requests/                               - Crear solicitud (cliente; congela la referencia y notifica)
- GET    /api/requests/quote-limits/                  - Tarifa mínima y tope (app anterior)
- POST   /api/requests/{id}/quote/                    - Cotizar con motivo y agenda (trabajador)
- POST   /api/requests/{id}/quote/accept/             - Aceptar cotización y elegir método de pago (cliente)
- POST   /api/requests/{id}/quote/reject/             - Rechazar cotización (cliente)
- POST   /api/requests/{id}/schedule/                 - Reprogramar (trabajador; avisa al cliente)
- POST   /api/requests/{id}/cancel/                   - Cancelar con motivo (cliente o trabajador)
- POST   /api/requests/{id}/requote/                  - Re-cotizar una vez en camino o en progreso (trabajador)
- POST   /api/requests/{id}/requote/accept/           - Aceptar la re-cotización; cambia el precio (cliente)
- POST   /api/requests/{id}/requote/reject/           - Rechazar la re-cotización; queda el precio original (cliente)
- POST   /api/requests/{id}/payment-method/           - Cambiar método de pago antes de terminar (cliente)
- POST   /api/requests/{id}/cash-received/            - «Recibí el pago» en efectivo (trabajador; avisa al cliente)
- POST   /api/requests/{id}/rating/                   - Calificar servicio pagado o en efectivo registrado (cliente)

NOTIFICATIONS:
- POST   /api/notifications/                          - Notificar al otro participante (FCM desde el backend)
"""
