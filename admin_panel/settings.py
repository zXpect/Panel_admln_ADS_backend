import os
from pathlib import Path

import dj_database_url
from decouple import config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-default-key')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1',
                       cast=lambda v: [s.strip() for s in v.split(',') if s.strip()])
# Render define el dominio del servicio (ads-api.onrender.com) en esta variable
RENDER_EXTERNAL_HOSTNAME = config('RENDER_EXTERNAL_HOSTNAME', default='')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party apps
    'rest_framework',
    'corsheaders',
    'rest_framework_simplejwt',
    
    # Local apps
    'worker_verification',
    'payments',
    'pricing',
    'pqr',
    'accounts',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Sirve los estáticos del admin de Django en Render (sin nginx)
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware', 
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'admin_panel.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'admin_panel.wsgi.application'

# Database
# PostgreSQL en Render con DATABASE_URL (D23); sin ella, SQLite local
DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ==================== REST FRAMEWORK ====================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
    # Límites por endpoint (ScopedRateThrottle). Caché local: en producción con
    # varios workers de gunicorn conviene una caché compartida (Redis/BD).
    'DEFAULT_THROTTLE_RATES': {
        'payments': '30/min',
        'payments_webhook': '120/min',
        'service_requests': '30/min',
        'catalog': '60/min',   # público, por IP (DEF-17)
        'ratings': '10/min',
        'notifications': '60/min',
        'pqr': '20/min',
        'account': '5/min',
        'reminders': '10/min',
        # Panel admin: login por IP (fuerza bruta) y el resto por usuario
        'panel_login': '10/min',
        'panel': '300/min',
    },
}

# ==================== JWT SETTINGS ====================
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=5),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
}

# ==================== CORS SETTINGS ====================
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000',
    cast=lambda v: [s.strip() for s in v.split(',')]
)

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-request-id',
]

# ==================== FIREBASE SETTINGS ====================
FIREBASE_CONFIG = {
    'CREDENTIALS_PATH': config('FIREBASE_CREDENTIALS_PATH', default='firebase-credentials.json'),
    'DATABASE_URL': config('FIREBASE_DATABASE_URL', default=''),
    'STORAGE_BUCKET': config('FIREBASE_STORAGE_BUCKET', default=''),
}

# ==================== RECORDATORIOS (HU-17) ====================
# Secreto que comparte el programador externo (GitHub Actions) para llamar
# POST /api/internal/reminders/. Vacío: la ruta responde 404.
REMINDERS_TOKEN = config('REMINDERS_TOKEN', default='')

# ==================== PAYMENTS SETTINGS ====================
DJANGO_ENV = config('DJANGO_ENV', default='development')

# PAGOS_MODO=mock|wompi. El mock está prohibido en producción (ver payments/guards.py)
PAYMENTS = {
    'MODE': config('PAGOS_MODO', default='mock'),
    'CURRENCY': 'COP',
    'WOMPI': {
        'PUBLIC_KEY': config('WOMPI_PUBLIC_KEY', default=''),
        'PRIVATE_KEY': config('WOMPI_PRIVATE_KEY', default=''),
        'EVENTS_SECRET': config('WOMPI_EVENTS_SECRET', default=''),
        'INTEGRITY_SECRET': config('WOMPI_INTEGRITY_SECRET', default=''),
        'BASE_URL': config('WOMPI_BASE_URL', default='https://sandbox.wompi.co/v1'),
    },
    # URL pública https del backend: Wompi vuelve a <base>/api/payments/return/,
    # que abre la app (no acepta el deep link adsapp:// como redirect-url).
    # En Render se deduce de RENDER_EXTERNAL_HOSTNAME.
    'PUBLIC_BASE_URL': config(
        'PUBLIC_BASE_URL',
        default=f"https://{RENDER_EXTERNAL_HOSTNAME}" if RENDER_EXTERNAL_HOSTNAME else ''),
    'MOCK': {
        'EVENTS_SECRET': config('MOCK_EVENTS_SECRET', default=''),
        'INTEGRITY_SECRET': config('MOCK_INTEGRITY_SECRET', default=''),
        # URL con la que el teléfono/emulador llega al backend (emulador: http://10.0.2.2:8000)
        'CHECKOUT_BASE_URL': config('MOCK_CHECKOUT_BASE_URL', default='http://localhost:8000'),
    },
}

# ==================== LOGGING ====================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs/debug.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
        },
        'worker_verification': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
        },
        'payments': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
        },
    },
}

# Crear directorio de logs si no existe
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# ==================== PRODUCTION SETTINGS ====================
# Estas configuraciones se activan cuando DJANGO_ENV=production

DJANGO_ENV = config('DJANGO_ENV', default='development')

if DJANGO_ENV == 'production':
    DEBUG = False

    from django.core.exceptions import ImproperlyConfigured
    if SECRET_KEY == 'django-insecure-default-key':
        raise ImproperlyConfigured('Define SECRET_KEY en producción')

    # Seguridad adicional para producción
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

    # HTTPS: Render termina TLS en su proxy y avisa con X-Forwarded-Proto
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    # El chequeo de salud de Render llega por HTTP interno
    SECURE_REDIRECT_EXEMPT = [r'^api/health/$']
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    CSRF_TRUSTED_ORIGINS = config(
        'CSRF_TRUSTED_ORIGINS', default='',
        cast=lambda v: [s.strip() for s in v.split(',') if s.strip()])
    if RENDER_EXTERNAL_HOSTNAME:
        # El admin de Django (formularios con CSRF) en el dominio de Render
        CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

    # Estáticos comprimidos y con hash (requiere collectstatic en el build)
    STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
    }

    # Throttling compartido entre los workers de gunicorn (requiere createcachetable)
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
            'LOCATION': 'django_cache',
        }
    }

    # Logging más restrictivo en producción
    LOGGING['loggers']['django']['level'] = 'WARNING'
    LOGGING['loggers']['worker_verification']['level'] = 'INFO'