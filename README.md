# Worker Verification Admin Panel

Panel de administración para gestión y verificación de trabajadores, documentos y clientes utilizando Django REST Framework y Firebase.

## Tabla de Contenidos

- [Características](#características)
- [Tecnologías](#tecnologías)
- [Requisitos Previos](#requisitos-previos)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Uso](#uso)
- [API Endpoints](#api-endpoints)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Modelos de Datos](#modelos-de-datos)
- [Servicios](#servicios)
- [Seguridad](#seguridad)
- [Logging](#logging)
- [Contribuir](#contribuir)

## Características

- 🔐 Autenticación JWT con Simple JWT
- 👷 Gestión completa de trabajadores
- 📄 Sistema de verificación de documentos
- 👥 Administración de clientes
- 📊 Dashboard con estadísticas en tiempo real
- 🔥 Integración completa con Firebase (Realtime Database & Storage)
- 🌍 CORS configurado para desarrollo y producción
- 📝 Logging detallado
- ✅ Validación de datos con serializers

## Tecnologías

- **Backend**: Django 5.0, Django REST Framework
- **Base de Datos**: Firebase Realtime Database
- **Almacenamiento**: Firebase Storage
- **Autenticación**: JWT (Simple JWT)
- **Base de Datos Local**: SQLite (para usuarios de Django)
- **Lenguaje**: Python 3.11

## Requisitos Previos

- Python 3.11 (con 3.13 o 3.14 falla la instalación: `Pillow==10.2.0` y `pandas==2.2.0` no tienen paquetes para esas versiones)
- pip (gestor de paquetes de Python)
- Cuenta de Firebase con proyecto configurado
- Credenciales de Firebase (archivo JSON)

## Instalación

### 1. Clonar el repositorio

```bash
git clone -b develop https://github.com/zXpect/Panel_admln_ADS_backend.git
cd Panel_admln_ADS_backend
```

### 2. Crear entorno virtual

```bash
python -m venv venv
# En Windows con varias versiones instaladas: py -3.11 -m venv venv

# En Windows
venv\Scripts\activate

# En Linux/Mac
source venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

**Dependencias principales:**
```
Django>=5.0
djangorestframework
django-cors-headers
djangorestframework-simplejwt
firebase-admin
python-decouple
```

### 4. Migraciones de base de datos

```bash
python manage.py makemigrations
python manage.py migrate
```

### 5. Crear superusuario

```bash
python manage.py createsuperuser
```

## Configuración

### 1. Variables de Entorno

Copiar la plantilla y llenar los valores (todas las claves están comentadas en
`.env.example`; las del módulo de pagos, en `.env.payments.example`):

```bash
cp .env.example .env
```

No subir nunca el `.env` ni la llave de Firebase: ambos están en `.gitignore`.

### 2. Configuración de Firebase

1. Ir a Firebase Console
2. Crear o seleccionar proyecto
3. Ir a Configuración del proyecto > Cuentas de servicio
4. Generar nueva clave privada
5. Descargar el archivo JSON
6. Guardar como `serviceAccountKey.json` en `backend/` (o cambiar `FIREBASE_CREDENTIALS_PATH`)

### 3. Estructura de Firebase Database

```
Firebase Realtime Database:
├── User/
│   ├── Trabajadores/
│   │   └── {workerId}/
│   │       ├── name
│   │       ├── lastName
│   │       ├── email
│   │       ├── work
│   │       ├── isAvailable
│   │       ├── isOnline
│   │       ├── latitude
│   │       ├── longitude
│   │       ├── rating
│   │       ├── totalRatings
│   │       └── verificationStatus/
│   │           ├── status
│   │           └── submittedAt
│   └── Clientes/
│       └── {clientId}/
│           ├── name
│           ├── lastName
│           └── email
└── WorkerDocuments/
    └── {workerId}/
        ├── hojaDeVida/
        │   ├── id
        │   ├── fileUrl
        │   ├── status
        │   └── uploadedAt
        ├── antecedentesJudiciales/
        │   ├── id
        │   ├── fileUrl
        │   ├── status
        │   └── uploadedAt
        └── certificaciones/
            ├── titulos/
            │   └── {tituloId}/
            └── cartasRecomendacion/
                └── {cartaId}/
```

## Uso

### Iniciar servidor de desarrollo

```bash
python manage.py runserver
```

El servidor estará disponible en: `http://localhost:8000`

### Acceder al admin de Django

```
URL: http://localhost:8000/admin/
Usuario: (el creado con createsuperuser)
```

## API Endpoints

### Autenticación

#### Obtener Token JWT
```http
POST /api/auth/token/
Content-Type: application/json

{
  "username": "admin",
  "password": "password"
}

Response:
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

#### Refrescar Token
```http
POST /api/auth/token/refresh/
Content-Type: application/json

{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

### Trabajadores

#### Listar Trabajadores
```http
GET /api/workers/
Authorization: Bearer {token}

Query Parameters:
- category: Filtrar por categoría
- available: true/false
- online: true/false
- search: término de búsqueda

Response:
{
  "success": true,
  "count": 10,
  "data": [...]
}
```

#### Obtener Trabajador
```http
GET /api/workers/{id}/
Authorization: Bearer {token}
```

#### Crear Trabajador
```http
POST /api/workers/
Authorization: Bearer {token}
Content-Type: application/json

{
  "id": "worker123",
  "name": "Juan",
  "lastName": "Pérez",
  "email": "juan@example.com",
  "work": "Plomero",
  "phone": "3001234567",
  "pricePerHour": 25000,
  "latitude": 5.34851,
  "longitude": -73.902605
}
```

#### Actualizar Trabajador
```http
PATCH /api/workers/{id}/
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "Juan Carlos",
  "pricePerHour": 30000
}
```

#### Actualizar Disponibilidad
```http
PATCH /api/workers/{id}/availability/
Authorization: Bearer {token}
Content-Type: application/json

{
  "isAvailable": true
}
```

#### Actualizar Estado de Verificación
```http
PATCH /api/workers/{id}/verification_status/
Authorization: Bearer {token}
Content-Type: application/json

{
  "status": "approved"
}

Valores permitidos: "documents_submitted", "approved", "rejected"
```

#### Actualizar Estado en Línea
```http
PATCH /api/workers/{id}/online_status/
Authorization: Bearer {token}
Content-Type: application/json

{
  "isOnline": true
}
```

#### Actualizar Ubicación
```http
PATCH /api/workers/{id}/location/
Authorization: Bearer {token}
Content-Type: application/json

{
  "latitude": 5.34851,
  "longitude": -73.902605
}
```

#### Agregar Calificación
```http
POST /api/workers/{id}/add_rating/
Authorization: Bearer {token}
Content-Type: application/json

{
  "rating": 4.5
}
```

#### Obtener Estadísticas
```http
GET /api/workers/statistics/
Authorization: Bearer {token}

Response:
{
  "success": true,
  "data": {
    "total": 100,
    "available": 75,
    "online": 20,
    "by_category": {
      "Plomero": 30,
      "Electricista": 25,
      "Carpintero": 45
    }
  }
}
```

#### Eliminar Trabajador
```http
DELETE /api/workers/{id}/
Authorization: Bearer {token}
```

### Documentos

#### Documentos Pendientes
```http
GET /api/documents/pending/
Authorization: Bearer {token}

Response:
{
  "success": true,
  "count": 5,
  "data": [...]
}
```

#### Documentos por Trabajador
```http
GET /api/documents/worker/{workerId}/
Authorization: Bearer {token}
```

#### Hoja de Vida
```http
GET /api/documents/worker/{workerId}/hoja-vida/
Authorization: Bearer {token}
```

#### Antecedentes Judiciales
```http
GET /api/documents/worker/{workerId}/antecedentes/
Authorization: Bearer {token}
```

#### Títulos
```http
GET /api/documents/worker/{workerId}/titulos/
Authorization: Bearer {token}
```

#### Cartas de Recomendación
```http
GET /api/documents/worker/{workerId}/cartas/
Authorization: Bearer {token}
```

#### Crear Documento
```http
POST /api/documents/
Authorization: Bearer {token}
Content-Type: application/json

{
  "id": "doc123",
  "workerId": "worker123",
  "documentType": "hoja_de_vida",
  "category": "hojaDeVida",
  "fileName": "cv.pdf",
  "fileUrl": "https://storage.googleapis.com/...",
  "fileType": "application/pdf",
  "fileSize": 204800
}
```

#### Aprobar Documento
```http
POST /api/documents/approve/
Authorization: Bearer {token}
Content-Type: application/json

{
  "workerId": "worker123",
  "category": "hojaDeVida",
  "subcategory": null,
  "documentId": "doc123",
  "reviewerId": "admin123"
}
```

#### Rechazar Documento
```http
POST /api/documents/reject/
Authorization: Bearer {token}
Content-Type: application/json

{
  "workerId": "worker123",
  "category": "hojaDeVida",
  "subcategory": null,
  "documentId": "doc123",
  "reviewerId": "admin123",
  "reason": "El documento no es legible"
}
```

#### Verificar Documentos Requeridos
```http
GET /api/documents/worker/{workerId}/check-requirements/
Authorization: Bearer {token}

Response:
{
  "success": true,
  "data": {
    "hasHojaVida": true,
    "hasAntecedentes": true,
    "hasTitulo": false,
    "cartasCount": 3,
    "hasMinimumCartas": true,
    "isComplete": true
  }
}
```

#### Eliminar Documento
```http
DELETE /api/documents/delete/
Authorization: Bearer {token}
Content-Type: application/json

{
  "workerId": "worker123",
  "category": "hojaDeVida",
  "subcategory": null,
  "documentId": "doc123"
}
```

#### Obtener URL de Archivo
```http
GET /api/documents/file-url/?workerId=xxx&category=xxx&filename=xxx
Authorization: Bearer {token}

Response:
{
  "success": true,
  "url": "https://storage.googleapis.com/..."
}
```

### Clientes

#### Listar Clientes
```http
GET /api/clients/
Authorization: Bearer {token}

Query Parameters:
- search: término de búsqueda

Response:
{
  "success": true,
  "count": 50,
  "data": [...]
}
```

#### Obtener Cliente
```http
GET /api/clients/{id}/
Authorization: Bearer {token}
```

#### Contar Clientes
```http
GET /api/clients/count/
Authorization: Bearer {token}

Response:
{
  "success": true,
  "count": 50
}
```

### Dashboard

#### Estadísticas Generales
```http
GET /api/dashboard/stats/
Authorization: Bearer {token}

Response:
{
  "success": true,
  "data": {
    "workers": {
      "total": 100,
      "available": 75,
      "online": 20,
      "byCategory": {
        "Plomero": 30,
        "Electricista": 25
      }
    },
    "clients": {
      "total": 50
    },
    "documents": {
      "pendingTotal": 15,
      "pendingByType": {
        "hojaDeVida": 5,
        "antecedentesJudiciales": 4,
        "titulos": 3,
        "cartasRecomendacion": 3
      }
    }
  }
}
```

### Pagos, cotización y API de la app móvil

App `payments/`. Los endpoints de la app móvil se autentican con el **ID token
de Firebase** (`Authorization: Bearer <idToken>`, RS256); los del panel, con el
JWT de `/api/auth/token/`. Todos tienen límite de peticiones (`429` al excederlo).
La pasarela se elige con `PAGOS_MODO` (`mock` | `wompi`); ver `.env.payments.example`.

Flujo: el trabajador cotiza → el cliente acepta → el servicio avanza hasta
`completed` → el cliente paga → el cliente califica.

| Método | Ruta | Quién | Qué hace |
|---|---|---|---|
| `GET` | `/api/requests/quote-limits/?service_type=X` | App | Rango de precio permitido (COP) |
| `POST` | `/api/requests/{id}/quote/` | App (trabajador) | `{"quoted_price": 85000}` en COP enteros. Si la solicitud estaba `pending`, pasa a `accepted` |
| `POST` | `/api/requests/{id}/quote/accept/` | App (cliente) | Acepta la cotización; queda inmutable |
| `POST` | `/api/requests/{id}/quote/reject/` | App (cliente) | `{"reason": "..."}`; el trabajador puede volver a cotizar |
| `POST` | `/api/payments/` | App (cliente) | `{"service_request_id": "...", "redirect_url": "adsapp://..."}` → `reference`, `checkout_url`. El monto lo calcula el servidor (cotización aceptada); un pago abierto de menos de 30 min se reutiliza |
| `GET` | `/api/payments/{reference}/` | App (cliente/trabajador) o panel | Estado del pago; el panel ve además el historial de eventos |
| `GET` | `/api/payments/?status=&service_request_id=` | Panel | Listado paginado |
| `POST` | `/api/requests/{id}/rating/` | App (cliente) | `{"rating": 1-5, "comment": "..."}`; requiere el servicio pagado. Recalcula el promedio del trabajador |
| `POST` | `/api/notifications/` | App | `{"request_id": "...", "type": "new_request\|request_accepted\|request_rejected\|status_change"}`. FCM desde el backend; el servidor decide destinatario y texto |
| `POST` | `/api/payments/webhook/` | Pasarela | Eventos de Wompi/mock; se autentica por checksum |
| `GET/POST` | `/api/payments/mock-checkout/{reference}/` | Navegador | Checkout simulado (solo `PAGOS_MODO=mock`) |

Errores: `{"success": false, "error": "..."}` (o `"errors"` de validación) con
`400` datos inválidos, `401` sin token válido, `403` no es el participante
correcto, `404` no existe, `409` el estado de la solicitud no lo permite.

Rangos de precio configurables en el admin de Django (`SystemConfig`):
`quote_min_price_cop` (por defecto 1000), `quote_max_price_cop` (por defecto
5000000) y `quote_price_ranges` (JSON por tipo de servicio, p. ej.
`{"Plomería": {"min": 30000, "max": 800000}}`).

En Firebase, `requests/{id}` gana los campos `quoted_price`, `quote_status`
(`quoted`/`accepted`/`rejected`), `payment_status`
(`pending`/`approved`/`declined`/`error`/`voided`) y `payment_reference`, que
solo escribe el backend (ver `firebase/README.md`).

Pruebas manuales del mock: `python manage.py mock_payment <request_id> <monto_cop>`.

## Estructura del Proyecto

```
admin_panel/
├── admin_panel/
│   ├── __init__.py
│   ├── settings.py          # Configuración del proyecto
│   ├── urls.py              # URLs principales
│   ├── wsgi.py
│   └── asgi.py
├── worker_verification/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── models.py            # Modelos Django
│   ├── urls.py              # URLs de la app
│   ├── views/
│   │   ├── __init__.py
│   │   ├── worker_views.py  # Vistas de trabajadores
│   │   ├── document_views.py # Vistas de documentos
│   │   ├── client_views.py   # Vistas de clientes
│   │   └── dashboard_views.py # Vistas de dashboard
│   ├── serializers/
│   │   ├── __init__.py
│   │   ├── worker_serializers.py
│   │   ├── document_serializers.py
│   │   └── client_serializers.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── firebase_service.py   # Servicio base Firebase
│   │   ├── worker_service.py     # Lógica de trabajadores
│   │   ├── document_service.py   # Lógica de documentos
│   │   └── client_service.py     # Lógica de clientes
│   └── migrations/
├── logs/                    # Archivos de log
├── media/                   # Archivos media
├── staticfiles/            # Archivos estáticos
├── manage.py
├── requirements.txt
├── .env                    # Variables de entorno
├── firebase-credentials.json
└── README.md
```

## Modelos de Datos

### VerificationLog

Registra el historial de verificaciones de documentos.

```python
{
    "worker_id": "worker123",
    "document_type": "hoja_de_vida",
    "action": "approved",  # approved, rejected, pending
    "reviewer": User,
    "reason": "Opcional",
    "created_at": datetime
}
```

### SystemConfig

Almacena configuraciones del sistema.

```python
{
    "key": "max_file_size",
    "value": "10485760",
    "description": "Tamaño máximo de archivo en bytes",
    "updated_at": datetime
}
```

## Servicios

### FirebaseService

Servicio base que maneja todas las operaciones con Firebase:
- Conexión a Realtime Database
- Operaciones CRUD
- Gestión de Storage
- Generación de URLs firmadas

### WorkerService

Gestiona operaciones de trabajadores:
- CRUD completo
- Búsquedas y filtros
- Actualización de estado
- Estadísticas

### DocumentService

Maneja la gestión de documentos:
- Carga de documentos
- Verificación de requisitos
- Aprobación/Rechazo
- Gestión de archivos en Storage

### ClientService

Administra operaciones de clientes:
- Listado y búsqueda
- Obtención de detalles
- Conteo

## Seguridad

### Autenticación JWT

- Access token válido por 5 horas
- Refresh token válido por 1 día
- Algoritmo HS256
- Blacklist después de rotación

### CORS

Configurado para aceptar peticiones desde:
- http://localhost:3000
- http://127.0.0.1:3000

### Validaciones

- Validación de tipos de archivo permitidos
- Validación de tamaño máximo (10MB)
- Validación de datos con serializers
- Sanitización de inputs

## Logging

El sistema registra eventos en:

**Archivo**: `logs/debug.log`

**Niveles**:
- DEBUG: Información detallada
- INFO: Confirmación de operaciones
- WARNING: Advertencias
- ERROR: Errores capturados

**Formato**:
```
INFO 2025-01-20 10:30:45 worker_service Retrieved 100 workers
ERROR 2025-01-20 10:31:12 document_service Error approving document: File not found
```

## Testing

```bash
# Ejecutar tests
python manage.py test

# Con cobertura
coverage run --source='.' manage.py test
coverage report
```

## Documentación Adicional

### Reglas de Documentos Requeridos

Un trabajador está **completamente verificado** cuando:
1. ✅ Tiene Hoja de Vida (obligatorio)
2. ✅ Tiene Antecedentes Judiciales (obligatorio)
3. ✅ Tiene Título académico O al menos 3 cartas de recomendación

### Estados de Documentos

- `pending`: Documento cargado, esperando revisión
- `approved`: Documento aprobado por revisor
- `rejected`: Documento rechazado con razón

### Estados de Verificación de Trabajador

- `documents_submitted`: Trabajador ha enviado documentos
- `approved`: Trabajador verificado y aprobado
- `rejected`: Trabajador rechazado

## Solución de Problemas

### Error: Firebase no inicializa

**Solución**: Verificar que `firebase-credentials.json` existe y tiene las credenciales correctas.

### Error: CORS

**Solución**: Agregar el origen en `CORS_ALLOWED_ORIGINS` en `.env`

### Error: Token inválido

**Solución**: Refrescar el token usando `/api/auth/token/refresh/`

## Licencia

Este proyecto es privado y confidencial.

## Contribuir

1. Fork el proyecto
2. Crear rama de feature (`git checkout -b feature/AmazingFeature`)
3. Commit cambios siguiendo la [convención de commits](#convención-de-commits)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abrir Pull Request

### Convención de Commits

Este proyecto sigue [Conventional Commits](https://www.conventionalcommits.org/es/). El mensaje debe tener el formato:

```
<tipo>(<scope>): <descripción corta>

[cuerpo opcional]

[footer opcional]
```

#### Tipos

| Tipo       | Uso                                                                 |
|------------|----------------------------------------------------------------------|
| `feat`     | Nueva funcionalidad                                                  |
| `fix`      | Corrección de un bug                                                 |
| `refactor` | Cambio de código que no arregla un bug ni agrega funcionalidad       |
| `perf`     | Cambio que mejora el rendimiento                                     |
| `docs`     | Cambios solo de documentación (README, comentarios, etc.)            |
| `style`    | Cambios de formato (espacios, comas, etc.) sin afectar la lógica     |
| `test`     | Agregar o corregir tests                                             |
| `build`    | Cambios en dependencias o sistema de build (`requirements.txt`, etc.)|
| `ci`       | Cambios en configuración de integración continua                    |
| `chore`    | Tareas de mantenimiento que no afectan `src` ni tests                |
| `revert`   | Revierte un commit anterior                                          |

#### Scopes usados en este proyecto

Corresponden a los módulos de `worker_verification/`:

- `workers` — trabajadores
- `documents` — documentos y verificación
- `clients` — clientes
- `dashboard` — estadísticas y dashboard
- `auth` — autenticación/JWT
- `settings` — configuración del proyecto (`admin_panel/settings.py`, `urls.py`)
- `firebase` — integración con Firebase (Realtime Database / Storage)

#### Reglas

- Descripción corta en modo imperativo, sin punto final: `add`, `fix`, `update` (no `added`, `fixed`).
- Máximo ~72 caracteres en la primera línea.
- Un commit = un cambio lógico coherente.
- Si el cambio rompe compatibilidad, agregar `!` después del scope (`feat(auth)!: ...`) y describir el impacto en el footer con `BREAKING CHANGE:`.

#### Ejemplos

```
feat(settings): add project-level URL routing with JWT and worker_verification
fix(documents): validate file size before upload to Firebase Storage
docs(readme): document verification status endpoint
refactor(workers): extract availability logic into WorkerService
chore(build): bump djangorestframework-simplejwt to 5.3
```

## Contacto

Para soporte o consultas, contactar al equipo de desarrollo.

---

**Última actualización**: Octubre 2025
**Versión**: 1.0.0