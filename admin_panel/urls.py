"""
URL configuration for admin_panel project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.evaluators import PanelTokenObtainPairSerializer
from payments.views.reminder_views import RemindersRunView


class PanelLoginView(TokenObtainPairView):
    """Login del panel con límite de intentos por IP (10 por minuto); el token lleva el rol."""
    serializer_class = PanelTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'panel_login'


def health(request):
    """Chequeo de salud de Render: sin autenticación ni acceso a datos."""
    return JsonResponse({'status': 'ok'})


urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    path('api/health/', health, name='health'),
    
    # JWT Authentication
    path('api/auth/token/', PanelLoginView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Pricing App (catálogo y estimado; antes de payments.request_urls)
    path('api/', include('pricing.urls')),

    # Payments App
    path('api/payments/', include('payments.urls')),

    # Recordatorios (HU-17): los dispara un programador externo con REMINDERS_TOKEN
    path('api/internal/reminders/', RemindersRunView.as_view(), name='reminders-run'),

    # PQR App
    path('api/pqr/', include('pqr.urls')),

    # Cuenta de la app (eliminar mi cuenta)
    path('api/', include('accounts.urls')),
    path('api/', include('payments.request_urls')),

    # Worker Verification App
    path('api/', include('worker_verification.urls')),
]

# Servir archivos estáticos y media en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
