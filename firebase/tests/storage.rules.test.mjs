import { test, before, after } from 'node:test';
import { readFileSync } from 'node:fs';
import {
  initializeTestEnvironment, assertSucceeds, assertFails,
} from '@firebase/rules-unit-testing';
import { ref, uploadBytes, getBytes, deleteObject } from 'firebase/storage';

let env;
const WORKER = 'worker1', CLIENT = 'client1';
const PDF = { contentType: 'application/pdf' };
const JPG = { contentType: 'image/jpeg' };
const small = new Uint8Array([1, 2, 3]);
const big = new Uint8Array(11 * 1024 * 1024);

before(async () => {
  env = await initializeTestEnvironment({
    projectId: 'demo-ads',
    storage: {
      host: '127.0.0.1', port: 9199,
      rules: readFileSync(new URL('../storage.rules', import.meta.url), 'utf8'),
    },
  });
});
after(async () => env.cleanup());

const st = (uid) => (uid ? env.authenticatedContext(uid) : env.unauthenticatedContext()).storage();

test('documentos: solo el trabajador dueño sube y lee', async () => {
  const path = `worker_documents/${WORKER}/hojaDeVida/cv.pdf`;
  await assertSucceeds(uploadBytes(ref(st(WORKER), path), small, PDF));
  await assertSucceeds(getBytes(ref(st(WORKER), path)));
  await assertFails(getBytes(ref(st(CLIENT), path)));
  await assertFails(uploadBytes(ref(st(CLIENT), `worker_documents/${WORKER}/hojaDeVida/x.pdf`), small, PDF));
  await assertFails(getBytes(ref(st(null), path)));
});

test('documentos: tipo y tamaño limitados', async () => {
  await assertFails(uploadBytes(ref(st(WORKER), `worker_documents/${WORKER}/a/x.exe`), small, { contentType: 'application/octet-stream' }));
  await assertFails(uploadBytes(ref(st(WORKER), `worker_documents/${WORKER}/a/big.pdf`), big, PDF));
});

test('foto de cliente: dueño escribe, sesión lee', async () => {
  const path = `client_images/${CLIENT}/profile_${CLIENT}_1.jpg`;
  await assertSucceeds(uploadBytes(ref(st(CLIENT), path), small, JPG));
  await assertSucceeds(getBytes(ref(st(WORKER), path)));
  await assertFails(uploadBytes(ref(st(WORKER), path), small, JPG));
  await assertFails(uploadBytes(ref(st(CLIENT), `client_images/${CLIENT}/doc.pdf`), small, PDF));
});

test('foto de trabajador: el nombre debe llevar su uid', async () => {
  await assertSucceeds(uploadBytes(ref(st(WORKER), `worker_profiles/profile_${WORKER}_1.jpg`), small, JPG));
  await assertFails(uploadBytes(ref(st(CLIENT), `worker_profiles/profile_${WORKER}_2.jpg`), small, JPG));
  await assertFails(deleteObject(ref(st(CLIENT), `worker_profiles/profile_${WORKER}_1.jpg`)));
});

test('rutas no declaradas cerradas', async () => {
  await assertFails(uploadBytes(ref(st(CLIENT), 'otra/cosa.jpg'), small, JPG));
});
