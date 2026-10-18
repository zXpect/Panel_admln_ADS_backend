# Reglas de seguridad de Firebase

Reglas de Realtime Database y Storage del proyecto ADS, con pruebas
automáticas contra el emulador oficial de Firebase.

El backend Django y el panel admin **no** se ven afectados: el backend usa el
SDK admin (`serviceAccountKey.json`), que no pasa por estas reglas.

| Archivo | Qué es |
|---|---|
| `build_rules.py` | **Fuente de verdad** de las reglas de Realtime Database. Genera los dos `.json`. |
| `database.rules.json` | Reglas finales (con cotización y pagos). Generado, no editar a mano. |
| `database.rules.stage1.json` | Etapa 1: igual que las finales, sin las dos compuertas que dependen de las fases 3 y 4. Generado. |
| `storage.rules` | Reglas de Storage (documentos y fotos de perfil). |
| `tests/` | Pruebas de las reglas (`node:test` + `@firebase/rules-unit-testing`). |

## Problema actual

Las reglas publicadas hoy tienen en la raíz `".read": true, ".write": true`:

- **Cualquiera en internet, sin cuenta, puede leer y escribir toda la base**:
  teléfonos, correos y direcciones de clientes y trabajadores, solicitudes,
  tokens FCM.
- En Realtime Database un permiso concedido en un nodo padre **no se puede
  quitar** en un hijo. Mientras la raíz sea `true`, ninguna otra regla protege
  nada; por ejemplo, cualquiera podría escribir `payment_status: approved`.
- Las reglas actuales nombran `tokens` y `service_requests`, pero la app usa
  `Tokens` y `requests` (las rutas distinguen mayúsculas). Hoy funciona solo
  porque la raíz está abierta.

## Qué garantizan las reglas nuevas

**Realtime Database**
- Todo cerrado por defecto; solo se abren los nodos que usa la app.
- `requests`:
  - Las listas solo se leen con una consulta filtrada por el propio uid
    (`orderByChild('client_id' | 'worker_id').equalTo(uid)`); una solicitud
    individual solo la leen su cliente y su trabajador.
  - El cliente crea solicitudes propias en `pending`, sin campos de cotización
    ni de pago.
  - **Los campos de cotización (`quoted_price`, `quote_status`, `quoted_at`,
    `quote_accepted_at`, `quote_rejection_reason`) y de pago (`payment_status`,
    `payment_reference`, `payment_updated_at`) solo los escribe el backend.**
  - Transiciones de `status` por rol: el cliente cancela mientras no haya precio
    acordado (`pending`, o `accepted` con la cotización pendiente o rechazada);
    el trabajador sigue `pending → accepted|rejected → on_the_way → in_progress → completed`,
    sin saltar estados. Nadie cambia `client_id` ni `worker_id`, ni borra solicitudes.
  - Final: iniciar el viaje exige `quote_status == 'accepted'`, y la
    calificación (`is_rated`, `client_rating`, `client_comment`, `rated_at`) solo
    la escribe el backend (`POST /api/requests/<id>/rating/`, que exige el
    servicio pagado y recalcula el promedio). Etapa 1: el cliente la escribe una
    sola vez sobre un servicio completado.
- `User/Clientes/<uid>`: solo su dueño.
- `User/Trabajadores`: lo lee cualquier usuario con sesión (el cliente busca
  trabajadores). El trabajador edita su perfil, pero **no** su `rating`,
  `totalRatings` ni `isActive`, y en `verificationStatus.status` solo puede poner
  `documents_submitted`; aprobar o rechazar lo hace solo el panel.
- `notifications/<uid>`: historial que escribe el backend al enviar cada push.
  Solo su dueño lo lee y solo puede poner `read: true` en una notificación
  existente; no crea, edita ni borra notificaciones.
- `WorkerDocuments/<uid>`: solo su dueño. Puede subir o resubir documentos en
  `pending`, pero no cambiar `status` a `approved`/`rejected` ni escribir
  `reviewedBy`/`reviewedAt`.
- `active_workers` (GeoFire) y `Tokens`: cada usuario escribe solo lo suyo.
  Final: `Tokens/<uid>` solo lo lee su dueño, porque FCM sale del backend
  (`POST /api/notifications/`); etapa 1: lo lee cualquier usuario con sesión.
- Final: el rating del trabajador solo lo cambia el backend. Etapa 1: el cliente
  puede sumar una calificación (`totalRatings + 1`, promedio entre 0 y 5).

**Storage**
- `worker_documents/<uid>/...`: solo el dueño; PDF/JPG/PNG de menos de 10 MB.
- `client_images/<uid>/...` y `worker_profiles/profile_<uid>_*.jpg`: escribe
  solo el dueño (imágenes de menos de 5 MB); lee cualquier usuario con sesión.
- Todo lo demás, cerrado.

## Cambios requeridos en la app (`ADSv`)

Sin estos cambios, publicar las reglas **rompe la app**. Se verificó leyendo
el código; las rutas son relativas a `app/src/main/java/com/project/ads/`.

**Estado: implementados** en la rama `fix/firebase-rules-compat` de `ADSv`
(compila con `./gradlew compileDebugJavaWithJavac`).

| # | Archivo | Problema con las reglas nuevas | Cambio |
|---|---|---|---|
| 1 | `activities/client/MyRequestsActivity.java:167` | Lee todo `requests` y filtra en el teléfono → `permission_denied` | `child("requests").orderByChild("client_id").equalTo(uid)` |
| 2 | `activities/worker/ActiveServicesActivity.java:162` | Igual | `orderByChild("worker_id").equalTo(uid)` |
| 3 | `activities/worker/PendingRequestsActivity.java:187` | Igual | `orderByChild("worker_id").equalTo(uid)` |
| 4 | `activities/LoginActivity.java` (`resetPassword` → `verifyEmailInDatabase`) | La **recuperación de contraseña** consulta `User/Clientes` y `User/Trabajadores` por email sin sesión. Además de fallar, permite saber qué correos están registrados. (El login en sí ya inicia sesión primero y comprueba el rol por uid) | Enviar el correo directamente con `sendPasswordResetEmail` y mostrar siempre un mensaje neutro, exista o no la cuenta |
| 5 | `activities/client/VerifyRequestActivity.java:259` | Lee el nodo `users`, que no existe (hoy devuelve vacío y se usan valores por defecto; con las reglas falla y **no se pueden crear solicitudes**) | Leer el cliente de `User/Clientes/<uid>` y el trabajador de `User/Trabajadores/<workerId>` |

Los cambios 1 a 3 aprovechan los índices `.indexOn` de `client_id`/`worker_id`,
que además evitan descargar todas las solicitudes de todos los usuarios.

Lo demás de la app ya es compatible (verificado con las pruebas): creación de
solicitudes, aceptar/rechazar, avance de estados, cancelación desde `pending`,
registro de trabajadores y clientes, subida de documentos, GeoFire y tokens.

## Hallazgo crítico: credencial de administrador dentro del APK

`providers/FirebaseAuthProvider.java` carga `app/src/main/assets/serviceAccountKey.json`
para enviar notificaciones FCM desde el teléfono. Que el archivo esté en
`.gitignore` no lo protege: **va dentro de cada APK**, y cualquiera que lo
descomprima obtiene una credencial de servicio con la que se puede saltar todas
las reglas de esta carpeta (el alcance `firebase.messaging` lo fija la app, no la
llave).

Corrección:
1. ✅ Backend (Fase 3): `POST /api/notifications/` envía FCM con
   `firebase_admin.messaging`, autenticado con el ID token de Firebase; el
   servidor decide destinatario y texto y valida el rol de quien notifica. Las
   notificaciones de cotización y pago las dispara el propio backend.
2. ✅ App (Fase 4, rama `feature/payments` de `ADSv`): `NotificationProvider`
   llama a ese endpoint; se eliminaron `FirebaseAuthProvider`,
   `FCMAuthInterceptor`, `IFCMApi`, `RetrofitClient`, `AuthInterceptor` y
   `google-auth-library`, y el build ignora `assets/serviceAccountKey.json`
   (`androidResources.ignoreAssetsPattern`). Falta borrar la copia local del
   archivo en cada equipo de desarrollo.
3. **Revocar esa llave** en Google Cloud Console → IAM → Cuentas de servicio →
   Claves, y generar otra solo para el backend. Toda llave que haya salido en
   un APK debe considerarse comprometida.
4. Después, cerrar la lectura de `Tokens/<uid>` a solo su dueño (en
   `build_rules.py`, nodo `Tokens`).

## Estado

**Publicadas en producción el 2026-10-06:** `database.rules.json` (finales) y
`storage.rules`, junto con la versión de la app de la rama `feature/payments`.
Verificado: sin sesión, lectura y escritura de la base dan `401` y Storage `403`;
flujo completo (solicitud → cotización → servicio → pago → calificación)
probado en dos teléfonos.

**Sprint 4 (generadas el 2026-10-12, SIN publicar):** `database.rules.json` ya
incluye lo siguiente. Se publica solo cuando la app de la rama
`feature/task-catalog` de `ADSv` esté instalada en los dos teléfonos: la app de
`feature/payments` crea solicitudes y cancela escribiendo en Firebase, y dejaría
de poder hacerlo.
- La app ya no crea solicitudes: las crea `POST /api/requests/`.
- El cliente no cambia `status` (cancelar es `POST /api/requests/<id>/cancel/`) y
  el trabajador ya no pasa `pending → accepted` (aceptar es cotizar). El trabajador
  conserva `pending → rejected`, `accepted → on_the_way` (con cotización aceptada),
  `on_the_way → in_progress` e `in_progress → completed`.
- Campos que solo escribe el backend: `service_category`, `task_items`, `lat`,
  `lng`, `quote_reference`, `quote_is_adjusted`, `quote_adjustment_reason_*`,
  `scheduled_at`, `estimated_duration_min`, `rescheduled_at`, `reschedule_count`,
  `cancelled_by`, `cancellation_reason_*`, `cancelled_at`, `requote`,
  `search_started_at`, `worker_selected_at`. Los que son objetos (`task_items`,
  `quote_reference`, `requote`) se bloquean con `.validate: false` en el hijo,
  porque `.val()` no compara objetos.
- `database.rules.stage1.json` no cambia (es histórica).

## Plan de despliegue

**Etapa 1 — ahora (antes de las fases 3 y 4 de pagos)**
1. Aplicar en la app los cambios 1 a 5 y publicar esa versión.
2. Publicar `database.rules.stage1.json` y `storage.rules` (ver "Cómo publicar").
3. Probar: login de cliente y trabajador, crear solicitud, aceptar, avanzar
   estados, calificar, subir documentos, ver trabajadores en el mapa.

Versiones viejas de la app (sin los cambios 1 a 5) dejarán de mostrar las listas de
solicitudes y de crear solicitudes en cuanto se publiquen las reglas.

**Etapa 2 — con la Fase 4 (app que cotiza, paga, califica y notifica vía backend;
rama `feature/payments` de `ADSv`)**
- Publicar `database.rules.json` junto con esa versión de la app. Activa:
  cotización aceptada para iniciar el viaje, calificación y rating del
  trabajador solo desde el backend, y `Tokens` legible solo por su dueño.

**En paralelo, lo antes posible**: corregir el hallazgo crítico (FCM en el backend y revocar la llave).

## Cómo publicar

Desde la consola (lo más simple):
- Realtime Database → Reglas → pegar el contenido del `.json` → Publicar.
- Storage → Reglas → pegar `storage.rules` → Publicar.

La consola guarda el historial de versiones; para revertir, se elige la
versión anterior desde ahí.

Con la CLI (requiere `firebase login` y el id del proyecto):

```bash
npx firebase deploy --only database,storage --project <id-del-proyecto>
```

`firebase.json` apunta a `database.rules.json` (final). Para publicar la etapa 1
por CLI, cambiar temporalmente esa ruta a `database.rules.stage1.json`.

## Cómo modificar y probar

Requisitos: Node 18+ y Java 11+ (para el emulador).

```bash
python build_rules.py        # regenera los .json después de editar build_rules.py
npm install                  # la primera vez
npm test                     # reglas finales + Storage
npm run test:stage1          # reglas de etapa 1
```

## Riesgos residuales conocidos

- **Calificación del trabajador (solo etapa 1)**: con la app actual el cliente
  actualiza `rating`/`totalRatings` desde el teléfono. Las reglas solo permiten
  sumar una calificación cada vez con un promedio entre 0 y 5, pero no pueden
  comprobar que sea correcto. Se resuelve en la etapa 2: el backend registra la
  calificación y recalcula el promedio en una transacción.
- **Datos de trabajadores visibles**: `User/Trabajadores` lo lee cualquier
  usuario con sesión, incluidos email y teléfono. Si se quiere minimizar, separar
  un perfil público (nombre, oficio, foto, rating) del privado.
- **Fotos de perfil de trabajadores**: la ruta `worker_profiles/` no tiene
  carpeta por uid; el dueño se valida por el nombre del archivo
  (`profile_<uid>_...`). Conviene migrar a `worker_profiles/<uid>/...`.
