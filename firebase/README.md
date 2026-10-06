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
  - **`quoted_price`, `quote_status`, `payment_status`, `payment_reference` y
    `payment_updated_at` solo los escribe el backend.**
  - Transiciones de `status` por rol: el cliente solo cancela desde `pending`;
    el trabajador sigue `pending → accepted|rejected → on_the_way → in_progress → completed`,
    sin saltar estados. Nadie cambia `client_id` ni `worker_id`, ni borra solicitudes.
  - Final: iniciar el viaje exige `quote_status == 'accepted'`; calificar exige
    `status == 'completed'` y `payment_status == 'approved'`. Una calificación
    no se edita después.
- `User/Clientes/<uid>`: solo su dueño.
- `User/Trabajadores`: lo lee cualquier usuario con sesión (el cliente busca
  trabajadores). El trabajador edita su perfil, pero **no** su `rating`,
  `totalRatings` ni `isActive`, y en `verificationStatus.status` solo puede poner
  `documents_submitted`; aprobar o rechazar lo hace solo el panel.
- `WorkerDocuments/<uid>`: solo su dueño. Puede subir o resubir documentos en
  `pending`, pero no cambiar `status` a `approved`/`rejected` ni escribir
  `reviewedBy`/`reviewedAt`.
- `active_workers` (GeoFire) y `Tokens`: cada usuario escribe solo lo suyo.

**Storage**
- `worker_documents/<uid>/...`: solo el dueño; PDF/JPG/PNG de menos de 10 MB.
- `client_images/<uid>/...` y `worker_profiles/profile_<uid>_*.jpg`: escribe
  solo el dueño (imágenes de menos de 5 MB); lee cualquier usuario con sesión.
- Todo lo demás, cerrado.

## Cambios requeridos en la app (`ADSv`)

Sin estos cambios, publicar las reglas **rompe la app**. Se verificó leyendo
el código; las rutas son relativas a `app/src/main/java/com/project/ads/`.

| # | Archivo | Problema con las reglas nuevas | Cambio |
|---|---|---|---|
| 1 | `activities/client/MyRequestsActivity.java:167` | Lee todo `requests` y filtra en el teléfono → `permission_denied` | `child("requests").orderByChild("client_id").equalTo(uid)` |
| 2 | `activities/worker/ActiveServicesActivity.java:162` | Igual | `orderByChild("worker_id").equalTo(uid)` |
| 3 | `activities/worker/PendingRequestsActivity.java:187` | Igual | `orderByChild("worker_id").equalTo(uid)` |
| 4 | `activities/LoginActivity.java:375` y `:401` (`verifyEmailInDatabase`) | Consulta `User/Clientes` y `User/Trabajadores` por email **antes de iniciar sesión**. Además de fallar, permite saber qué correos están registrados | Iniciar sesión primero y después comprobar el rol leyendo `User/<Clientes|Trabajadores>/<uid>` (la app ya lo hace en `:222`) |
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

Corrección recomendada (prioridad alta, encaja con la Fase 3 de pagos, que ya
abre el canal app → backend):
1. Enviar las notificaciones desde el backend con `firebase_admin.messaging`
   (endpoint autenticado con el Firebase ID token, o disparadas por el propio
   backend al cambiar el estado de una solicitud o de un pago).
2. Quitar de la app `FirebaseAuthProvider`, `FCMAuthInterceptor`, el uso de
   `IFCMApi` y el archivo `assets/serviceAccountKey.json`.
3. **Revocar esa llave** en Google Cloud Console → IAM → Cuentas de servicio →
   Claves, y generar otra solo para el backend. Toda llave que haya salido en
   un APK debe considerarse comprometida.
4. Después, cerrar la lectura de `Tokens/<uid>` a solo su dueño (en
   `build_rules.py`, nodo `Tokens`).

## Plan de despliegue

**Etapa 1 — ahora (antes de las fases 3 y 4 de pagos)**
1. Aplicar en la app los cambios 1 a 5 y publicar esa versión.
2. Publicar `database.rules.stage1.json` y `storage.rules` (ver "Cómo publicar").
3. Probar: login de cliente y trabajador, crear solicitud, aceptar, avanzar
   estados, calificar, subir documentos, ver trabajadores en el mapa.

Versiones viejas de la app (sin los cambios 1 a 5) dejarán de mostrar las listas de
solicitudes y de crear solicitudes en cuanto se publiquen las reglas.

**Etapa 2 — con las fases 3 y 4 de pagos**
- Publicar `database.rules.json` (activa las dos compuertas: cotización
  aceptada para iniciar el viaje y pago aprobado para calificar) junto con la
  versión de la app que ya cotiza y paga.

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

- **Calificación del trabajador (interino)**: el cliente actualiza
  `rating`/`totalRatings` del trabajador desde la app
  (`RequestProvider.rateRequest`). Las reglas solo permiten sumar una
  calificación cada vez (`totalRatings + 1`) con un promedio entre 0 y 5, pero no
  pueden comprobar que el promedio sea correcto ni que venga de una solicitud
  real. Lo correcto es que el backend recalcule el promedio al registrar la
  calificación (Fase 3) y quitar esas tres excepciones de `build_rules.py`.
- **Datos de trabajadores visibles**: `User/Trabajadores` lo lee cualquier
  usuario con sesión, incluidos email y teléfono. Si se quiere minimizar, separar
  un perfil público (nombre, oficio, foto, rating) del privado.
- **Fotos de perfil de trabajadores**: la ruta `worker_profiles/` no tiene
  carpeta por uid; el dueño se valida por el nombre del archivo
  (`profile_<uid>_...`). Conviene migrar a `worker_profiles/<uid>/...`.
