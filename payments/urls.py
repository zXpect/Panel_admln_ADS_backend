from django.urls import path

from .views import MockCheckoutView, PaymentWebhookView

app_name = 'payments'

urlpatterns = [
    path('webhook/', PaymentWebhookView.as_view(), name='webhook'),
    path('mock-checkout/<str:reference>/', MockCheckoutView.as_view(), name='mock-checkout'),
]

"""
RUTAS DISPONIBLES:

PAYMENTS:
- POST   /api/payments/webhook/                  - Eventos de la pasarela (sin JWT; valida checksum)
- GET    /api/payments/mock-checkout/{reference}/ - Checkout simulado (solo PAGOS_MODO=mock)
- POST   /api/payments/mock-checkout/{reference}/ - Simular aprobado/rechazado/error
"""
