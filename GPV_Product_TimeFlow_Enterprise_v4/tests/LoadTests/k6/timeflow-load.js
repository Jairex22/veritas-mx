// Prueba de carga k6 · GPV Product TimeFlow (API REST)
// Ejecutar:  k6 run -e BASE_URL=https://servidor/api-timeflow -e VUS=200 -e DURATION=5m k6/timeflow-load.js
// Requisitos: API en modo DEMO o TEST con cuentas sintéticas y RateLimiting__LoginPermitsPerMinute alto para la prueba.
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = (__ENV.BASE_URL || 'http://localhost:5201').replace(/\/$/, '');
const PASSWORD = __ENV.PASSWORD || 'Demo#TimeFlow2026';

export const options = {
  scenarios: {
    usuarios: { executor: 'ramping-vus', startVUs: 0, stages: [
      { duration: '1m', target: Number(__ENV.VUS || 200) },
      { duration: __ENV.DURATION || '5m', target: Number(__ENV.VUS || 200) },
      { duration: '30s', target: 0 } ] },
  },
  thresholds: {
    'http_req_duration{tipo:consulta}': ['p(95)<2000'],
    'http_req_failed': ['rate<0.01'],
  },
};

export function setup() {
  const login = http.post(`${BASE}/api/v1/auth/login`, JSON.stringify({ email: 'admin.producto@demo.timeflow.example', password: PASSWORD }), { headers: { 'Content-Type': 'application/json' } });
  const token = login.json('accessToken');
  const res = http.get(`${BASE}/api/v1/admin/employees?pageSize=200`, { headers: { Authorization: `Bearer ${token}` } });
  return { emails: res.json('items').filter(e => e.isActive).map(e => e.email) };
}

export default function (data) {
  if (!__VU_TOKEN) {
    const email = data.emails[(__VU - 1) % data.emails.length];
    const r = http.post(`${BASE}/api/v1/auth/login`, JSON.stringify({ email, password: PASSWORD }), { headers: { 'Content-Type': 'application/json' }, tags: { tipo: 'login' } });
    __VU_TOKEN = r.json('accessToken');
  }
  const h = { headers: { Authorization: `Bearer ${__VU_TOKEN}` }, tags: { tipo: 'consulta' } };
  const today = new Date().toISOString().slice(0, 10);
  const pick = Math.random();
  let res;
  if (pick < 0.3) res = http.get(`${BASE}/api/v1/dashboard`, h);
  else if (pick < 0.55) res = http.get(`${BASE}/api/v1/requests?scope=Mine&pageSize=20`, h);
  else if (pick < 0.7) res = http.get(`${BASE}/api/v1/notifications/unread-count`, h);
  else if (pick < 0.85) res = http.get(`${BASE}/api/v1/calendar?from=${today}&to=${today}&scope=Team`, h);
  else res = http.get(`${BASE}/api/v1/vacations/balance`, h);
  check(res, { 'sin error de servidor': r => r.status < 500 });
  sleep(0.5 + Math.random() * 1.5);
}

let __VU_TOKEN = null;
