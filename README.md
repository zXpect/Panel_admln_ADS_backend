# Worker Verification Admin Panel

Panel de administración para gestión y verificación de trabajadores, documentos y clientes utilizando Django REST Framework y Firebase.

## 📋 Tabla de Contenidos

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

## ✨ Características

- 🔐 Autenticación JWT con Simple JWT
- 👷 Gestión completa de trabajadores
- 📄 Sistema de verificación de documentos
- 👥 Administración de clientes
- 📊 Dashboard con estadísticas en tiempo real
- 🔥 Integración completa con Firebase (Realtime Database & Storage)
- 🌍 CORS configurado para desarrollo y producción
- 📝 Logging detallado
- ✅ Validación de datos con serializers

## 🛠 Tecnologías

- **Backend**: Django 5.0, Django REST Framework
- **Base de Datos**: Firebase Realtime Database
- **Almacenamiento**: Firebase Storage
- **Autenticación**: JWT (Simple JWT)
- **Base de Datos Local**: SQLite (para usuarios de Django)
- **Lenguaje**: Python 3.x

## 📦 Requisitos Previos

- Python 3.8 o superior
- pip (gestor de paquetes de Python)
- Cuenta de Firebase con proyecto configurado
- Credenciales de Firebase (archivo JSON)

## 🚀 Instalación

### 1. Clonar el repositorio

```bash
git clone <url-del-repositorio>
cd admin_panel
```

### 2. Crear entorno virtual

```bash
python -m venv venv

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

## ⚙️ Configuración

### 1. Variables de Entorno

Crear un archivo `.env` en la raíz del proyecto:

```env
# Django
SECRET_KEY=tu-secret-key-super-segura
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# Firebase
FIREBASE_CREDENTIALS_PATH=firebase-credentials.json
FIREBASE_DATABASE_URL=https://tu-proyecto.firebaseio.com
FIREBASE_STORAGE_BUCKET=tu-proyecto.appspot.com
```

### 2. Configuración de Firebase

1. Ir a Firebase Console
2. Crear o seleccionar proyecto
3. Ir a Configuración del proyecto > Cuentas de servicio
4. Generar nueva clave privada
5. Descargar el archivo JSON
6. Guardar como `firebase-credentials.json` en la raíz del proyecto

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

## 🎯 Uso

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

## 🔌 API Endpoints

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

## 📁 Estructura del Proyecto

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

## 📊 Modelos de Datos

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

## 🔧 Servicios

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

## 🔒 Seguridad

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

## 📝 Logging

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

## 🧪 Testing

```bash
# Ejecutar tests
python manage.py test

# Con cobertura
coverage run --source='.' manage.py test
coverage report
```

## 📚 Documentación Adicional

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

## 🐛 Solución de Problemas

### Error: Firebase no inicializa

**Solución**: Verificar que `firebase-credentials.json` existe y tiene las credenciales correctas.

### Error: CORS

**Solución**: Agregar el origen en `CORS_ALLOWED_ORIGINS` en `.env`

### Error: Token inválido

**Solución**: Refrescar el token usando `/api/auth/token/refresh/`

## 📄 Licencia

Este proyecto es privado y confidencial.

## 👥 Contribuir

1. Fork el proyecto
2. Crear rama de feature (`git checkout -b feature/AmazingFeature`)
3. Commit cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abrir Pull Request

## 📧 Contacto

Para soporte o consultas, contactar al equipo de desarrollo.

---

**Última actualización**: Octubre 2025
**Versión**: 1.0.0