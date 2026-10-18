from django.urls import path

from .views import (
    MockCheckoutView,
    PaymentDetailView,
    PaymentListCreateView,
    PaymentWebhookView,
)

app_name = 'payments'

urlpatterns = [
    # Las rutas fijas van antes de <reference>/
    path('webhook/', PaymentWebhookView.as_view(), name='webhook'),
    path('mock-checkout/<str:reference>/', MockCheckoutView.as_view(), name='mock-checkout'),
    path('', PaymentListCreateView.as_view(), name='payment-list'),
    path('<str:reference>/', PaymentDetailView.as_view(), name='payment-detail'),
]

"""
RUTAS DISPONIBLES:

PAYMENTS:
- POST   /api/payments/                           - Iniciar pago (app, cliente; ID token de Firebase)
- GET    /api/payments/                           - Listar pagos (panel admin; ?status=&service_request_id=)
- GET    /api/payments/{reference}/               - Estado del pago (cliente/trabajador de la solicitud o panel)
- POST   /api/payments/webhook/                   - Eventos de la pasarela (sin JWT; valida checksum)
- GET    /api/payments/mock-checkout/{reference}/ - Checkout simulado (solo PAGOS_MODO=mock)
- POST   /api/payments/mock-checkout/{reference}/ - Simular aprobado/rechazado/error

Ver también payments/request_urls.py (/api/requests/, /api/notifications/)
"""
