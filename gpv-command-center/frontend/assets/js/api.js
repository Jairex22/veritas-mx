// Cliente HTTP: cookies de sesión HttpOnly + token CSRF en cabecera. Nunca almacena credenciales.
let csrfToken = null;
export function setCsrf(token) { csrfToken = token; }

export class ApiError extends Error {
  constructor(status, body) {
    const e = (body && body.error) || {};
    super(e.message || `Error HTTP ${status}`);
    this.status = status;
    this.code = e.code || "HTTP_" + status;
    this.details = e.details || {};
    this.correlationId = e.correlation_id || null;
  }
}

const listeners = new Set();
export function onUnauthorized(fn) { listeners.add(fn); }

export async function api(path, { method = "GET", body, params, signal } = {}) {
  let url = path;
  if (params) {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ""));
    if ([...qs].length) url += "?" + qs;
  }
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;
  let res;
  try {
    res = await fetch(url, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined, credentials: "same-origin", signal });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError(0, { error: { code: "NETWORK", message: "No hay comunicación con el servidor del Command Center." } });
  }
  let data = null;
  const text = await res.text();
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!res.ok) {
    const e = new ApiError(res.status, data);
    if (!e.correlationId) e.correlationId = res.headers.get("X-Correlation-ID");
    if (res.status === 401 && !path.startsWith("/api/auth/login")) listeners.forEach((fn) => fn(e));
    throw e;
  }
  return data;
}

export const get = (p, params, opts = {}) => api(p, { ...opts, params });
export const post = (p, body) => api(p, { method: "POST", body: body ?? {} });
