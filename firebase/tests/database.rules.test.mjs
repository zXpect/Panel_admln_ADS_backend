import { test, before, beforeEach, after } from 'node:test';
import { readFileSync } from 'node:fs';
import {
  initializeTestEnvironment, assertSucceeds, assertFails,
} from '@firebase/rules-unit-testing';
import {
  ref, get, set, update, remove, query, orderByChild, equalTo,
} from 'firebase/database';

// `npm run test:stage1` prueba la etapa 1 (sin compuertas de cotización/pago)
const STAGE1 = process.env.npm_lifecycle_event === 'test:stage1';
const RULES_FILE = STAGE1 ? 'database.rules.stage1.json' : 'database.rules.json';
const RULES = new URL(`../${RULES_FILE}`, import.meta.url);
const gated = STAGE1 ? assertSucceeds : assertFails;
let env;

const CLIENT = 'client1', WORKER = 'worker1', OTHER = 'intruder';
const REQ = 'req1';

before(async () => {
  env = await initializeTestEnvironment({
    projectId: 'demo-ads',
    database: { host: '127.0.0.1', port: 9000, rules: readFileSync(RULES, 'utf8') },
  });
});
after(async () => env.cleanup());

const db = (uid) => (uid ? env.authenticatedContext(uid) : env.unauthenticatedContext()).database();
const admin = async (fn) => env.withSecurityRulesDisabled(async (ctx) => fn(ctx.database()));

const baseRequest = (overrides = {}) => ({
  client_id: CLIENT, worker_id: WORKER, status: 'pending',
  service_type: 'Plomería', is_rated: false, timestamp: 1, ...overrides,
});

beforeEach(async () => {
  await env.clearDatabase();
  await admin(async (d) => {
    await set(ref(d, `requests/${REQ}`), baseRequest());
    await set(ref(d, `requests/reqOther`), baseRequest({ client_id: 'client2', worker_id: 'worker2' }));
    await set(ref(d, `User/Trabajadores/${WORKER}`), {
      name: 'W', rating: 4, totalRatings: 2, isActive: true,
      verificationStatus: { status: 'documents_submitted' },
    });
    await set(ref(d, `User/Clientes/${CLIENT}`), { name: 'C', email: 'c@x.co' });
  });
});

// ---------- acceso general ----------
test('sin sesión no se lee nada', async () => {
  await assertFails(get(ref(db(null), 'requests')));
  await assertFails(get(ref(db(null), 'User/Trabajadores')));
});

test('nodos no declarados están cerrados', async () => {
  await assertFails(get(ref(db(CLIENT), 'users/' + CLIENT)));
  await assertFails(set(ref(db(CLIENT), 'service_requests/x'), { a: 1 }));
});

// ---------- requests: lectura ----------
test('leer todo requests está prohibido', async () => {
  await assertFails(get(ref(db(CLIENT), 'requests')));
});
test('cliente consulta sus solicitudes por client_id', async () => {
  await assertSucceeds(get(query(ref(db(CLIENT), 'requests'), orderByChild('client_id'), equalTo(CLIENT))));
  await assertFails(get(query(ref(db(CLIENT), 'requests'), orderByChild('client_id'), equalTo('client2'))));
});
test('trabajador consulta sus solicitudes por worker_id', async () => {
  await assertSucceeds(get(query(ref(db(WORKER), 'requests'), orderByChild('worker_id'), equalTo(WORKER))));
});
test('solo los participantes leen una solicitud', async () => {
  await assertSucceeds(get(ref(db(CLIENT), `requests/${REQ}`)));
  await assertSucceeds(get(ref(db(WORKER), `requests/${REQ}`)));
  await assertFails(get(ref(db(OTHER), `requests/${REQ}`)));
});

// ---------- requests: creación ----------
test('cliente crea solicitud propia en pending', async () => {
  await assertSucceeds(set(ref(db(CLIENT), 'requests/new1'), baseRequest()));
});
test('no se crea a nombre de otro ni con campos de pago/cotización', async () => {
  await assertFails(set(ref(db(OTHER), 'requests/new2'), baseRequest()));
  await assertFails(set(ref(db(CLIENT), 'requests/new3'), baseRequest({ payment_status: 'approved' })));
  await assertFails(set(ref(db(CLIENT), 'requests/new4'), baseRequest({ quoted_price: 1000 })));
  await assertFails(set(ref(db(CLIENT), 'requests/new5'), baseRequest({ status: 'completed' })));
});

// ---------- requests: campos protegidos ----------
test('nadie desde la app toca payment_status, quoted_price ni quote_status', async () => {
  await admin((d) => update(ref(d, `requests/${REQ}`), { quoted_price: 50000, quote_status: 'quoted' }));
  for (const uid of [CLIENT, WORKER]) {
    await assertFails(update(ref(db(uid), `requests/${REQ}`), { payment_status: 'approved' }));
    await assertFails(update(ref(db(uid), `requests/${REQ}`), { quoted_price: 1 }));
    await assertFails(update(ref(db(uid), `requests/${REQ}`), { quote_status: 'accepted' }));
    await assertFails(set(ref(db(uid), `requests/${REQ}/quoted_price`), null));
  }
});
test('no se borran solicitudes', async () => {
  await assertFails(remove(ref(db(CLIENT), `requests/${REQ}`)));
});

// ---------- requests: transiciones ----------
test('cliente cancela solo en pending', async () => {
  await assertSucceeds(update(ref(db(CLIENT), `requests/${REQ}`), { status: 'cancelled', cancelled_at: 2 }));
  await admin((d) => update(ref(d, `requests/${REQ}`), { status: 'accepted' }));
  await assertFails(update(ref(db(CLIENT), `requests/${REQ}`), { status: 'cancelled' }));
});
test('cliente no avanza estados del trabajador', async () => {
  await assertFails(update(ref(db(CLIENT), `requests/${REQ}`), { status: 'accepted' }));
});
test('trabajador acepta y no inicia viaje sin cotización aceptada', async () => {
  await assertSucceeds(update(ref(db(WORKER), `requests/${REQ}`), { status: 'accepted', last_updated: 3 }));
  await gated(update(ref(db(WORKER), `requests/${REQ}`), { status: 'on_the_way' }));
  await admin((d) => update(ref(d, `requests/${REQ}`), { status: 'accepted', quoted_price: 50000, quote_status: 'accepted' }));
  await assertSucceeds(update(ref(db(WORKER), `requests/${REQ}`), { status: 'on_the_way', started_trip_at: 4 }));
  await assertSucceeds(update(ref(db(WORKER), `requests/${REQ}`), { status: 'in_progress' }));
  await assertSucceeds(update(ref(db(WORKER), `requests/${REQ}`), { status: 'completed' }));
});
test('trabajador no salta estados ni reasigna la solicitud', async () => {
  await assertFails(update(ref(db(WORKER), `requests/${REQ}`), { status: 'completed' }));
  await assertFails(update(ref(db(WORKER), `requests/${REQ}`), { worker_id: OTHER }));
});

// ---------- requests: calificación ----------
test('calificar exige completado y pagado; luego no se edita', async () => {
  await admin((d) => update(ref(d, `requests/${REQ}`), { status: 'completed' }));
  const rating = { is_rated: true, client_rating: 5, client_comment: 'ok', rated_at: 5 };
  if (!STAGE1) {
    await assertFails(update(ref(db(CLIENT), `requests/${REQ}`), rating));
  }
  await admin((d) => update(ref(d, `requests/${REQ}`), { payment_status: 'approved' }));
  await assertFails(update(ref(db(WORKER), `requests/${REQ}`), rating));
  await assertSucceeds(update(ref(db(CLIENT), `requests/${REQ}`), rating));
  await assertFails(update(ref(db(CLIENT), `requests/${REQ}`), { client_rating: 1 }));
});

// ---------- User/Trabajadores ----------
test('trabajador no se aprueba a sí mismo ni cambia su rating', async () => {
  const me = `User/Trabajadores/${WORKER}`;
  await assertFails(update(ref(db(WORKER), me), { 'verificationStatus/status': 'approved' }));
  await assertSucceeds(update(ref(db(WORKER), me), { 'verificationStatus/status': 'documents_submitted', 'verificationStatus/submittedAt': 9 }));
  await assertFails(update(ref(db(WORKER), me), { rating: 5 }));
  await assertFails(update(ref(db(WORKER), me), { isActive: false }));
  await assertSucceeds(update(ref(db(WORKER), me), { isAvailable: true, isOnline: true, timestamp: 9 }));
});
test('registro de trabajador nuevo con rating 0', async () => {
  await assertSucceeds(set(ref(db('worker9'), 'User/Trabajadores/worker9'), { name: 'N', rating: 0, totalRatings: 0 }));
  await assertFails(set(ref(db('worker8'), 'User/Trabajadores/worker8'), { name: 'N', rating: 5, totalRatings: 10 }));
});
test('cliente actualiza promedio solo sumando una calificación (interino)', async () => {
  const w = `User/Trabajadores/${WORKER}`;
  await assertSucceeds(update(ref(db(CLIENT), w), { rating: 4.3, totalRatings: 3, timestamp: 9 }));
  await assertFails(update(ref(db(CLIENT), w), { rating: 5, totalRatings: 10 }));
  await assertFails(update(ref(db(CLIENT), w), { name: 'hack' }));
  await assertFails(update(ref(db(CLIENT), w), { 'verificationStatus/status': 'approved' }));
});
test('cualquier usuario con sesión lista trabajadores', async () => {
  await assertSucceeds(get(ref(db(CLIENT), 'User/Trabajadores')));
});

// ---------- Clientes, tokens, documentos, geofire ----------
test('datos de clientes solo para su dueño', async () => {
  await assertSucceeds(get(ref(db(CLIENT), `User/Clientes/${CLIENT}`)));
  await assertFails(get(ref(db(WORKER), `User/Clientes/${CLIENT}`)));
  await assertFails(get(ref(db(CLIENT), 'User/Clientes')));
});
test('tokens: cada quien escribe el suyo', async () => {
  await assertSucceeds(set(ref(db(CLIENT), `Tokens/${CLIENT}/token`), 't'));
  await assertFails(set(ref(db(CLIENT), `Tokens/${WORKER}/token`), 't'));
});
test('trabajador no aprueba sus propios documentos', async () => {
  const hv = `WorkerDocuments/${WORKER}/hojaDeVida`;
  const titulo = `WorkerDocuments/${WORKER}/certificaciones/titulos/doc1`;
  await assertSucceeds(set(ref(db(WORKER), hv), { status: 'pending', fileName: 'cv.pdf' }));
  await assertSucceeds(set(ref(db(WORKER), titulo), { status: 'pending', fileName: 't.pdf' }));
  await assertFails(update(ref(db(WORKER), hv), { status: 'approved' }));
  await assertFails(update(ref(db(WORKER), titulo), { status: 'approved' }));
  await assertFails(update(ref(db(WORKER), titulo), { reviewedBy: 'yo' }));
  // Tras un rechazo del panel, el trabajador puede volver a subirlo como pending
  await admin((d) => update(ref(d, hv), { status: 'rejected', reviewedBy: 'admin', reviewedAt: 7 }));
  await assertSucceeds(update(ref(db(WORKER), hv), { status: 'pending', fileName: 'cv2.pdf' }));
});

test('documentos y ubicación: solo el dueño escribe', async () => {
  await assertSucceeds(set(ref(db(WORKER), `WorkerDocuments/${WORKER}/hojaDeVida`), { status: 'pending' }));
  await assertFails(get(ref(db(CLIENT), `WorkerDocuments/${WORKER}`)));
  await assertSucceeds(set(ref(db(WORKER), `active_workers/${WORKER}`), { g: 'abc', l: [5, -73] }));
  await assertFails(set(ref(db(CLIENT), `active_workers/${WORKER}`), { g: 'abc', l: [5, -73] }));
  await assertSucceeds(get(ref(db(CLIENT), 'active_workers')));
});
