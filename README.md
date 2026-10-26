# ADS - API Backend

API REST del sistema ADS, una plataforma que conecta a clientes con trabajadores
independientes de reparaciones locativas (hogar y comercio) en Ubaté,
Cundinamarca. Este servicio, construido con Django y Django REST Framework,
atiende dos clientes:

- **Panel de administración web** (React): verificación documental de
  trabajadores, gestión de clientes, catálogo de servicios, parámetros de
  cotización, pagos, PQR y estadísticas. Se autentica con JWT.
- **Aplicación móvil Android**: creación de solicitudes, cotización, pagos,
  calificación, PQR y notificaciones push. Se autentica con el ID token de
  Firebase.

Los datos de dominio (trabajadores, clientes, solicitudes y documentos) viven en
Firebase Realtime Database y Firebase Storage; la base de datos relacional guarda
las cuentas del panel, el libro de pagos, las PQR, el catálogo de tarifas, la
configuración del sistema y la auditoría.

## Tabla de contenido

1. [Funcionalidades](#funcionalidades)
2. [Arquitectura](#arquitectura)
3. [Tecnologías](#tecnologías)
4. [Estructura del proyecto](#estructura-del-proyecto)
5. [Requisitos](#requisitos)
6. [Instalación](#instalación)
7. [Configuración](#configuración)
8. [Ejecución](#ejecución)
9. [Autenticación](#autenticación)
10. [Referencia de la API](#referencia-de-la-api)
11. [Formato de respuestas y errores](#formato-de-respuestas-y-errores)
12. [Límites de peticiones](#límites-de-peticiones)
13. [Modelo de datos](#modelo-de-datos)
14. [Pasarela de pagos](#pasarela-de-pagos)
15. [Reglas de seguridad de Firebase](#reglas-de-seguridad-de-firebase)
16. [Pruebas](#pruebas)
17. [Comandos de gestión](#comandos-de-gestión)
18. [Despliegue](#despliegue)
19. [Seguridad](#seguridad)
20. [Contribución](#contribución)
21. [Licencia](#licencia)

## Funcionalidades

- Autenticación del panel con JWT (access y refresh token, rotación y lista negra).
- Gestión de trabajadores: consulta, edición, estado de verificación,
  disponibilidad, ubicación y estadísticas.
- Carga masiva de trabajadores desde un archivo Excel con plantilla descargable.
- Verificación documental: revisión, aprobación y rechazo de hoja de vida,
  antecedentes judiciales, títulos y cartas de recomendación, con registro de
  auditoría por cada decisión.
- Consulta de clientes y suspensión o reactivación de cuentas.
- Tablero con estadísticas generales y tendencias semanales y mensuales.
- Catálogo de oficios y tareas con rangos de precio de referencia ajustados a
  Ubaté, y parámetros de cotización editables con historial de cambios.
- Ciclo de vida de la solicitud de servicio: creación, cotización, aceptación o
  rechazo, reprogramación, cancelación con motivo y una única re-cotización.
- Pagos en línea mediante Wompi (o una pasarela simulada en desarrollo) y
  registro de pagos en efectivo.
- Calificación del servicio por parte del cliente.
- Peticiones, quejas y reclamos (PQR) con plazo de respuesta de 15 días hábiles.
- Notificaciones push (Firebase Cloud Messaging) enviadas desde el servidor y
  recordatorios programados.
- Eliminación de la cuenta del usuario y de sus datos personales.

## Arquitectura

```
+---------------------+        JWT        +-------------------------+
| Panel admin (React) | ----------------> |                         |
+---------------------+                   |   API Django (este repo) | ---> PostgreSQL / SQLite
                                          |                         |
+---------------------+  ID token Firebase|                         | ---> Wompi (pagos)
| App Android (Java)  | ----------------> |                         |
+---------------------+                   +-------------------------+
          |                                            |
          |      SDK de Firebase (lectura/escritura)   |  SDK Admin de Firebase
          v                                            v
   +--------------------------------------------------------------+
   |  Firebase: Authentication, Realtime Database, Storage, FCM    |
   +--------------------------------------------------------------+
```

La aplicación móvil lee y escribe la mayor parte de sus datos directamente en
Firebase, protegida por las reglas de seguridad de `firebase/`. Las operaciones
que esas reglas reservan al servidor (cotización, pagos, calificación,
notificaciones y eliminación de cuenta) pasan por esta API.

## Tecnologías

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.11 |
| Framework | Django 5.0, Django REST Framework 3.14 |
| Autenticación | djangorestframework-simplejwt 5.3 (panel), Firebase ID token (app) |
| Datos de dominio | Firebase Realtime Database y Storage (firebase-admin 6.4) |
| Base de datos relacional | PostgreSQL en producción, SQLite en desarrollo |
| Pagos | Wompi (Web Checkout) y pasarela simulada para desarrollo |
| Procesamiento de Excel | pandas, openpyxl, xlrd |
| Servidor de producción | Gunicorn y WhiteNoise sobre Render |

## Estructura del proyecto

```
backend/
├── admin_panel/            Configuración del proyecto (settings, urls, wsgi)
├── worker_verification/    Trabajadores, documentos, clientes, tablero y carga masiva
│   ├── views/              Vistas y ViewSets de DRF
│   ├── serializers/        Validación de entrada y salida
│   ├── services/           Lógica de negocio y acceso a Firebase
│   └── tests/              Pruebas con un Firebase simulado en memoria
├── pricing/                Catálogo de oficios y tareas, estimados y configuración
├── payments/               Solicitudes de servicio, cotización, pagos, calificación,
│                           notificaciones y recordatorios
├── pqr/                    Peticiones, quejas y reclamos
├── accounts/               Eliminación de cuenta, estadísticas del trabajador y
│                           suspensión de cuentas
├── firebase/               Reglas de Realtime Database y Storage con sus pruebas
├── .github/workflows/      Disparo programado de recordatorios
├── manage.py
├── requirements.txt
└── render.yaml             Blueprint de despliegue en Render
```

Cada aplicación de Django sigue la misma organización en capas: `views/`
recibe la petición, `serializers/` valida los datos y `services/` contiene la
lógica de negocio.

## Requisitos

- Python 3.11. Con Python 3.13 o superior la instalación falla porque algunas
  dependencias fijadas (Pillow 10.2 y pandas 2.2) no publican paquetes para esas
  versiones.
- pip.
- Un proyecto de Firebase con Realtime Database, Storage y Authentication
  habilitados, y una clave de cuenta de servicio en formato JSON.
- Node.js 20 y Firebase CLI, solo para ejecutar las pruebas de las reglas de
  Firebase.

## Instalación

1. Clonar el repositorio:

   ```bash
   git clone https://github.com/zXpect/Panel_admln_ADS_backend.git
   cd Panel_admln_ADS_backend
   ```

2. Crear y activar un entorno virtual:

   ```bash
   python -m venv venv
   ```

   En Windows (con varias versiones de Python instaladas, usar `py -3.11 -m venv venv`):

   ```bash
   venv\Scripts\activate
   ```

   En Linux o macOS:

   ```bash
   source venv/bin/activate
   ```

3. Instalar las dependencias:

   ```bash
   pip install -r requirements.txt
   ```

4. Crear el archivo de entorno a partir de la plantilla y completar sus valores
   (ver [Configuración](#configuración)):

   ```bash
   cp .env.example .env
   ```

5. Copiar la clave de cuenta de servicio de Firebase en esta carpeta con el
   nombre `serviceAccountKey.json` (Consola de Firebase > Configuración del
   proyecto > Cuentas de servicio > Generar nueva clave privada).

6. Aplicar las migraciones. Incluyen la carga inicial del catálogo de oficios y
   tareas y de los parámetros del sistema:

   ```bash
   python manage.py migrate
   ```

7. Crear el usuario administrador con el que se ingresa al panel:

   ```bash
   python manage.py createsuperuser
   ```

## Configuración

La configuración se lee de variables de entorno o del archivo `.env`. Las
plantillas `.env.example`, `.env.payments.example` y `.env.production.example`
documentan cada variable.

| Variable | Descripción | Ejemplo |
|---|---|---|
| `SECRET_KEY` | Clave secreta de Django. Obligatoria en producción. | Valor aleatorio |
| `DEBUG` | Modo de depuración. | `True` |
| `DJANGO_ENV` | `development` o `production`. En producción activa HTTPS obligatorio, cookies seguras y HSTS. | `development` |
| `ALLOWED_HOSTS` | Hosts permitidos, separados por coma. Para el emulador de Android agregar `10.0.2.2`. | `localhost,127.0.0.1,10.0.2.2` |
| `CORS_ALLOWED_ORIGINS` | Orígenes permitidos para el panel web. | `http://localhost:3000` |
| `DATABASE_URL` | Cadena de conexión a PostgreSQL. Si no se define, se usa SQLite. | `postgres://...` |
| `FIREBASE_CREDENTIALS_PATH` | Ruta a la clave de cuenta de servicio. | `serviceAccountKey.json` |
| `FIREBASE_DATABASE_URL` | URL de Realtime Database. | `https://<proyecto>-default-rtdb.firebaseio.com` |
| `FIREBASE_STORAGE_BUCKET` | Bucket de Storage. | `<proyecto>.firebasestorage.app` |
| `PAGOS_MODO` | Pasarela de pagos: `mock` o `wompi`. | `mock` |
| `MOCK_EVENTS_SECRET`, `MOCK_INTEGRITY_SECRET` | Secretos de la pasarela simulada. | Valores aleatorios |
| `MOCK_CHECKOUT_BASE_URL` | URL con la que el teléfono llega al backend en desarrollo. | `http://10.0.2.2:8000` |
| `WOMPI_PUBLIC_KEY`, `WOMPI_PRIVATE_KEY` | Llaves de Wompi. | `pub_test_...`, `prv_test_...` |
| `WOMPI_EVENTS_SECRET`, `WOMPI_INTEGRITY_SECRET` | Secretos de eventos e integridad de Wompi. | `test_events_...` |
| `WOMPI_BASE_URL` | API de Wompi (Sandbox o producción). | `https://sandbox.wompi.co/v1` |
| `REMINDERS_TOKEN` | Secreto de la ruta de recordatorios. Vacío deshabilita la ruta. | Valor aleatorio |

El archivo `.env` y la clave de Firebase están excluidos del control de
versiones y nunca deben publicarse.

## Ejecución

Iniciar el servidor de desarrollo:

```bash
python manage.py runserver
```

La API queda disponible en `http://localhost:8000/api/` y el administrador de
Django en `http://localhost:8000/admin/`. Para que un teléfono físico en la
misma red acceda al servidor:

```bash
python manage.py runserver 0.0.0.0:8000
```

Comprobación de estado:

```bash
curl http://localhost:8000/api/health/
```

Respuesta esperada: `{"status": "ok"}`.

## Autenticación

La API usa dos esquemas, ambos con el encabezado `Authorization: Bearer <token>`:

| Cliente | Token | Cómo se obtiene |
|---|---|---|
| Panel de administración | JWT de simplejwt (HS256). Access de 5 horas, refresh de 1 día, con rotación y lista negra. | `POST /api/auth/token/` con usuario y contraseña de Django |
| Aplicación móvil | ID token de Firebase Authentication (RS256). | SDK de Firebase en el dispositivo |

Ejemplo de inicio de sesión del panel:

```http
POST /api/auth/token/
Content-Type: application/json

{
  "username": "admin",
  "password": "********"
}
```

```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOi...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOi..."
}
```

Renovación del token:

```http
POST /api/auth/token/refresh/
Content-Type: application/json

{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOi..."
}
```

## Referencia de la API

Todas las rutas comienzan con `/api/`. La columna "Acceso" indica quién puede
llamar cada ruta: **Panel** (JWT), **App** (ID token de Firebase), **Pública**
(sin autenticación) o un mecanismo propio.

### Sistema y autenticación

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| `GET` | `/api/health/` | Pública | Estado del servicio |
| `POST` | `/api/auth/token/` | Pública | Inicio de sesión del panel; devuelve `access` y `refresh` |
| `POST` | `/api/auth/token/refresh/` | Pública | Renueva el token de acceso |

### Trabajadores

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| `GET` | `/api/workers/` | Panel | Lista paginada. Filtros: `category`, `available`, `online`, `search` |
| `GET` | `/api/workers/{id}/` | Panel | Detalle del trabajador |
| `POST` | `/api/workers/` | Panel | Crea un trabajador |
| `PUT` / `PATCH` | `/api/workers/{id}/` | Panel | Actualiza el trabajador completo o campos puntuales |
| `DELETE` | `/api/workers/{id}/` | Panel | Elimina el trabajador y su cuenta de Firebase Authentication |
| `GET` | `/api/workers/statistics/` | Panel | Totales, disponibles, en línea y conteo por oficio |
| `PATCH` | `/api/workers/{id}/verification_status/` | Panel | Cambia el estado de verificación: `documents_submitted`, `approved` o `rejected`. Queda auditado |
| `PATCH` | `/api/workers/{id}/availability/` | Panel | `{"isAvailable": true}` |
| `PATCH` | `/api/workers/{id}/online_status/` | Panel | `{"isOnline": true}` |
| `PATCH` | `/api/workers/{id}/location/` | Panel | `{"latitude": 5.3085, "longitude": -73.8164}` |
| `POST` | `/api/workers/{id}/add_rating/` | Panel | Agrega una calificación al promedio |
| `GET` | `/api/workers/{id}/stats/` | App | Trabajos completados, calificación promedio y número de calificaciones |
| `POST` | `/api/workers/bulk-upload/` | Panel | Carga masiva desde Excel (`multipart/form-data`). Cada fila exige nombre, apellido, correo válido y oficio |
| `GET` | `/api/workers/bulk-upload-template/` | Panel | Descarga la plantilla de Excel |

### Documentos de verificación

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| `GET` | `/api/documents/pending/` | Panel | Documentos pendientes de revisión |
| `GET` | `/api/documents/worker/{workerId}/` | Panel | Todos los documentos de un trabajador |
| `GET` | `/api/documents/worker/{workerId}/hoja-vida/` | Panel | Hoja de vida |
| `GET` | `/api/documents/worker/{workerId}/antecedentes/` | Panel | Antecedentes judiciales |
| `GET` | `/api/documents/worker/{workerId}/titulos/` | Panel | Títulos académicos |
| `GET` | `/api/documents/worker/{workerId}/cartas/` | Panel | Cartas de recomendación |
| `GET` | `/api/documents/worker/{workerId}/check-requirements/` | Panel | Indica si el trabajador cumple los documentos mínimos |
| `POST` | `/api/documents/` | Panel | Registra un documento |
| `POST` | `/api/documents/approve/` | Panel | Aprueba un documento |
| `POST` | `/api/documents/reject/` | Panel | Rechaza un documento con motivo |
| `DELETE` | `/api/documents/delete/` | Panel | Elimina un documento |
| `GET` | `/api/documents/file-url/` | Panel | URL firmada del archivo. Parámetros: `workerId`, `category`, `filename` |

Ejemplo de aprobación. El revisor se toma del usuario autenticado, no del
cuerpo de la petición:

```http
POST /api/documents/approve/
Authorization: Bearer <access>
Content-Type: application/json

{
  "workerId": "uid_trabajador",
  "category": "hojaDeVida",
  "subcategory": null,
  "documentId": "doc123"
}
```

El rechazo usa el mismo cuerpo con el campo adicional `"reason"`. Un trabajador
cumple los requisitos cuando tiene hoja de vida, antecedentes judiciales y un
título académico o al menos tres cartas de recomendación.

### Clientes y cuentas

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| `GET` | `/api/clients/` | Panel | Lista paginada. Filtro: `search` |
| `GET` | `/api/clients/{id}/` | Panel | Detalle del cliente |
| `GET` | `/api/clients/count/` | Panel | Total de clientes |
| `PATCH` | `/api/admin/accounts/{uid}/status/` | Panel | Suspende o reactiva una cuenta de cliente o trabajador. Queda auditado |
| `POST` | `/api/accounts/deleted-status/` | Pública | `{"email": "..."}`. Indica si la cuenta de ese correo fue eliminada y por quién (panel o usuario); la app lo consulta cuando falla el inicio de sesión |
| `DELETE` | `/api/me/` | App | Elimina la cuenta del usuario autenticado y sus datos personales. Responde `204`, o `409` si tiene un servicio en curso |

### Tablero

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| `GET` | `/api/dashboard/stats/` | Panel | Totales de trabajadores, clientes y documentos pendientes |
| `GET` | `/api/dashboard/weekly-trends/` | Panel | Tendencias de la semana |
| `GET` | `/api/dashboard/monthly-trends/` | Panel | Tendencias del mes |
| `GET` | `/api/dashboard/activity-stats/` | Panel | Estadísticas de actividad |

### Catálogo, estimados y configuración

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| `GET` | `/api/catalog/` | Pública | Oficios y tareas activos con el rango de precio para Ubaté |
| `POST` | `/api/requests/estimate/` | App | Precio de referencia de las tareas elegidas; no crea la solicitud |
| `GET` | `/api/admin/catalog/` | Panel | Oficios y tareas, incluidos los inactivos |
| `PATCH` | `/api/admin/catalog/categories/{id}/` | Panel | Cambia nombre, orden o estado de un oficio |
| `POST` | `/api/admin/catalog/tasks/` | Panel | Crea una tarea |
| `PATCH` | `/api/admin/catalog/tasks/{id}/` | Panel | Edita o desactiva una tarea (las tareas no se eliminan) |
| `GET` | `/api/admin/config/` | Panel | Parámetros de cotización y búsqueda |
| `PATCH` | `/api/admin/config/{key}/` | Panel | Cambia un parámetro, con validación de formato y rango |
| `GET` | `/api/admin/audit/` | Panel | Historial de cambios. Filtro: `entity` |

Los precios se redondean a la centena con redondeo aritmético y nunca quedan
por debajo de la tarifa mínima por visita.

### Solicitudes de servicio

Todas las rutas de esta sección son de la aplicación móvil. El servidor valida
que quien llama sea el cliente o el trabajador de la solicitud y que el estado
de la solicitud permita la operación.

| Método | Ruta | Quién | Descripción |
|---|---|---|---|
| `POST` | `/api/requests/` | Cliente | Crea la solicitud con tareas, dirección y coordenadas; congela el precio de referencia y notifica al trabajador |
| `GET` | `/api/requests/quote-limits/` | Ambos | Tarifa mínima y tope de cotización. Parámetro: `service_type` |
| `POST` | `/api/requests/{id}/quote/` | Trabajador | Envía la cotización con motivo de ajuste y agenda |
| `POST` | `/api/requests/{id}/quote/accept/` | Cliente | Acepta la cotización y elige el método de pago (`digital` o `cash`) |
| `POST` | `/api/requests/{id}/quote/reject/` | Cliente | Rechaza la cotización; el trabajador puede volver a cotizar |
| `POST` | `/api/requests/{id}/schedule/` | Trabajador | Reprograma la visita y avisa al cliente |
| `POST` | `/api/requests/{id}/cancel/` | Ambos | Cancela con un motivo de la lista; el cliente solo antes de "en camino" |
| `POST` | `/api/requests/{id}/requote/` | Trabajador | Re-cotiza una sola vez, con el servicio en camino o en progreso |
| `POST` | `/api/requests/{id}/requote/accept/` | Cliente | Acepta la re-cotización; cambia el precio |
| `POST` | `/api/requests/{id}/requote/reject/` | Cliente | Rechaza la re-cotización; se conserva el precio original |
| `POST` | `/api/requests/{id}/payment-method/` | Cliente | Cambia el método de pago antes de terminar el servicio |
| `POST` | `/api/requests/{id}/cash-received/` | Trabajador | Registra el pago en efectivo y avisa al cliente |
| `POST` | `/api/requests/{id}/rating/` | Cliente | Califica de 1 a 5 un servicio pagado; recalcula el promedio del trabajador |
| `POST` | `/api/notifications/` | Ambos | Envía una notificación push a la otra parte. El servidor decide destinatario y texto |

Estados del servicio: `pending`, `accepted`, `on_the_way`, `in_progress`,
`completed` y `cancelled`. Ejemplo de cotización:

```http
POST /api/requests/{id}/quote/
Authorization: Bearer <id_token_firebase>
Content-Type: application/json

{
  "quoted_price": 85000,
  "adjustment_reason_code": "materiales",
  "adjustment_reason_text": "",
  "scheduled_at": 1793782800000,
  "estimated_duration_min": 90
}
```

Los precios se expresan en pesos colombianos enteros. `scheduled_at` es la
fecha y hora de llegada en milisegundos desde 1970 (UTC), futura y dentro de
los próximos 30 días. Motivos de ajuste: `materiales`, `dificultad`, `tiempo`,
`condiciones_lugar` y `otro` (este último exige texto).

### Pagos

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| `POST` | `/api/payments/` | App (cliente) | Inicia el pago de una solicitud. Devuelve `reference` y `checkout_url`. El monto lo calcula el servidor a partir de la cotización aceptada |
| `GET` | `/api/payments/` | Panel | Lista paginada con resumen de pagos aprobados. Filtros: `status`, `gateway`, `service_request_id`, `date_from`, `date_to` |
| `GET` | `/api/payments/{reference}/` | App o Panel | Estado del pago; el panel ve además el historial de eventos |
| `POST` | `/api/payments/webhook/` | Pasarela | Eventos de Wompi; se autentica por checksum |
| `GET` | `/api/payments/return/` | Navegador | Retorno del checkout; abre la aplicación (`adsapp://`) |
| `GET` / `POST` | `/api/payments/mock-checkout/{reference}/` | Navegador | Checkout simulado (solo con `PAGOS_MODO=mock`) |

Ejemplo:

```http
POST /api/payments/
Authorization: Bearer <id_token_firebase>
Content-Type: application/json

{
  "service_request_id": "-Nabc123",
  "redirect_url": "adsapp://payment-result"
}
```

### PQR

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| `POST` | `/api/pqr/` | App | Registra una PQR sobre una solicitud propia |
| `GET` | `/api/pqr/` | App o Panel | La app ve las propias; el panel ve todas. Filtro: `status` (`abierta`, `en_tramite`, `cerrada`) |
| `GET` | `/api/pqr/{id}/` | App o Panel | Detalle |
| `PATCH` | `/api/pqr/{id}/` | Panel | Pasa a trámite o cierra con respuesta; avisa al autor |

El plazo de respuesta se calcula en 15 días hábiles en hora de Colombia,
excluyendo fines de semana y festivos.

### Tareas internas

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| `POST` | `/api/internal/reminders/` | `REMINDERS_TOKEN` | Envía los recordatorios pendientes: servicio próximo, cotización sin responder y pago pendiente |

## Formato de respuestas y errores

Las respuestas exitosas siguen la forma:

```json
{
  "success": true,
  "data": { },
  "count": 20
}
```

`count` aparece en los listados. La paginación es por número de página, con 20
elementos por página (`?page=2`).

Los errores siguen la forma:

```json
{
  "success": false,
  "error": "Descripción del error"
}
```

Los errores de validación devuelven `"errors"` con el detalle por campo.

| Código | Significado |
|---|---|
| `400` | Datos inválidos |
| `401` | Token ausente, vencido o inválido |
| `403` | El usuario no tiene permiso sobre el recurso (por ejemplo, no es participante de la solicitud) |
| `404` | El recurso no existe |
| `409` | El estado actual de la solicitud no permite la operación |
| `429` | Se superó el límite de peticiones |

## Límites de peticiones

Todas las vistas aplican límites por ámbito (`ScopedRateThrottle`):

| Ámbito | Límite | Aplica a |
|---|---|---|
| `panel_login` | 10 por minuto, por IP | Inicio de sesión del panel |
| `panel` | 300 por minuto, por usuario | Rutas del panel |
| `catalog` | 60 por minuto, por IP | Catálogo público |
| `service_requests` | 30 por minuto | Solicitudes y estimados |
| `payments` | 30 por minuto | Pagos |
| `payments_webhook` | 120 por minuto | Webhook de la pasarela |
| `ratings` | 10 por minuto | Calificaciones |
| `notifications` | 60 por minuto | Notificaciones |
| `pqr` | 20 por minuto | PQR |
| `account` | 5 por minuto | Eliminación de cuenta |
| `account_check` | 10 por minuto, por IP | Consulta de cuenta eliminada |
| `reminders` | 10 por minuto | Recordatorios |

## Modelo de datos

### Firebase Realtime Database

```
User/
├── Trabajadores/{uid}     Perfil, oficios (categories), disponibilidad,
│                          ubicación, calificación y verificationStatus
└── Clientes/{uid}         Perfil del cliente
requests/{id}              Solicitud de servicio: tareas, estado, cotización
                           (quoted_price, quote_status) y pago
                           (payment_status, payment_reference)
WorkerDocuments/{uid}/     hojaDeVida, antecedentesJudiciales y
                           certificaciones (titulos, cartasRecomendacion)
Tokens/{uid}               Token FCM del dispositivo
notifications/{uid}        Bandeja de notificaciones del usuario
active_workers/            Índice geográfico (GeoFire) de trabajadores conectados
```

Los campos de cotización y pago de `requests/{id}` solo los escribe el backend;
las reglas de Firebase impiden que la aplicación los modifique.

### Base de datos relacional

| Aplicación | Modelos |
|---|---|
| `worker_verification` | `VerificationLog` (auditoría de verificación), `SystemConfig` (parámetros del sistema) |
| `pricing` | `ServiceCategory`, `Task`, `ConfigAuditLog` |
| `payments` | `Payment`, `PaymentEvent` |
| `pqr` | `PQR` |
| Django | `auth.User` (cuentas del panel) |

## Pasarela de pagos

La pasarela se selecciona con `PAGOS_MODO`:

- `mock`: pasarela simulada que replica la firma de integridad, los estados y
  los eventos de Wompi. Sirve para desarrollo y pruebas, y no puede iniciarse
  con `DJANGO_ENV=production`.
- `wompi`: integración con el Web Checkout de Wompi. Los eventos se verifican
  con `WOMPI_EVENTS_SECRET` y, antes de cerrar un pago pendiente vencido, se
  consulta la transacción en Wompi para conciliarla.

Flujo: el trabajador cotiza, el cliente acepta y elige el método de pago, el
servicio avanza hasta `completed`, el cliente paga en Wompi o el trabajador
registra el efectivo, y finalmente el cliente califica. El estado del pago se
refleja en `requests/{id}/payment_status` de Firebase.

En el panel de Wompi, la URL de eventos debe ser
`https://<host>/api/payments/webhook/`.

## Reglas de seguridad de Firebase

La carpeta `firebase/` contiene las reglas de Realtime Database y Storage que
usa la aplicación móvil, junto con sus pruebas contra el emulador oficial. Las
reglas de Realtime Database se generan con `build_rules.py`; los archivos
`.json` no se editan a mano. Ver `firebase/README.md` para el detalle.

```bash
cd firebase
npm install
npm test
```

## Pruebas

Ejecutar todas las pruebas del backend:

```bash
python manage.py test
```

Por aplicación:

```bash
python manage.py test worker_verification
python manage.py test payments
python manage.py test pricing
python manage.py test pqr
python manage.py test accounts
```

Las pruebas no requieren conexión con Firebase: usan un Firebase simulado en
memoria. Para medir la cobertura:

```bash
coverage run manage.py test
coverage report
```

## Comandos de gestión

| Comando | Descripción |
|---|---|
| `python manage.py send_reminders` | Envía los recordatorios pendientes |
| `python manage.py mock_payment <request_id> <monto_cop>` | Simula un pago con la pasarela de desarrollo |
| `python manage.py migrate_worker_categories` | Migra el oficio único de los trabajadores al campo de oficios múltiples |
| `python manage.py createsuperuser` | Crea un usuario del panel |

## Despliegue

El archivo `render.yaml` define un Blueprint de Render con el servicio web de la
API (Gunicorn) y una base de datos PostgreSQL.

1. En Render, crear un Blueprint (**New > Blueprint**) a partir de este repositorio.
2. Completar las variables marcadas como `sync: false`: `FIREBASE_DATABASE_URL`,
   `FIREBASE_STORAGE_BUCKET` y las cuatro llaves de Wompi. El dominio de Render se
   agrega solo a `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`.
3. En **Environment > Secret Files** del servicio, subir `serviceAccountKey.json`
   (queda en `/etc/secrets/serviceAccountKey.json`).
4. Desplegar. La compilación instala las dependencias y ejecuta `collectstatic`,
   `migrate` y `createcachetable`.
5. Verificar `https://<host>/api/health/`.
6. Crear el usuario del panel desde la consola del servicio con
   `python manage.py createsuperuser`.
7. Agregar la URL del panel web a `CORS_ALLOWED_ORIGINS`.
8. Configurar en el repositorio de GitHub los secretos `ADS_API_URL` y
   `REMINDERS_TOKEN` para que el flujo `.github/workflows/reminders.yml` envíe los
   recordatorios cada 30 minutos. GitHub solo ejecuta flujos programados desde la
   rama por defecto.

El plan gratuito de Render suspende el servicio sin tráfico; la primera
petición posterior tarda unos segundos.

## Seguridad

- Autenticación obligatoria en todas las rutas salvo las indicadas como públicas.
- Contraseñas del panel almacenadas con el hasher PBKDF2 de Django.
- Tokens JWT con vencimiento corto, rotación y lista negra.
- Verificación del ID token de Firebase en cada petición de la aplicación móvil y
  control de participante por solicitud.
- Documentos de los trabajadores servidos mediante URL firmadas de Firebase Storage.
- Registro de auditoría de cada decisión de verificación y de cada cambio de
  catálogo, configuración o estado de cuenta.
- Límites de peticiones por ámbito, incluido el inicio de sesión.
- En producción: HTTPS obligatorio, cookies seguras, HSTS y bloqueo de la
  pasarela simulada.
- Ningún secreto se versiona: `.env`, claves de Firebase y llaves de Wompi se
  entregan como variables de entorno o archivos secretos.

## Contribución

1. Crear una rama a partir de `develop`: `feature/<nombre-corto>` para
   funcionalidades o `fix/<nombre-corto>` para correcciones.
2. Hacer commits con el formato [Conventional Commits](https://www.conventionalcommits.org/es/):

   ```
   <tipo>(<alcance>): <descripción>
   ```

   Tipos: `feat`, `fix`, `refactor`, `perf`, `docs`, `style`, `test`, `build`,
   `ci`, `chore`, `revert`. Alcances habituales: `workers`, `documents`,
   `clients`, `dashboard`, `auth`, `payments`, `pricing`, `pqr`, `accounts`,
   `notifications`, `firebase`, `settings`.

3. Ejecutar las pruebas antes de abrir el Pull Request hacia `develop`.
4. La rama `main` se reserva para versiones publicadas.

## Licencia

Proyecto privado desarrollado como trabajo de grado en la Universidad de
Cundinamarca. Todos los derechos reservados.
