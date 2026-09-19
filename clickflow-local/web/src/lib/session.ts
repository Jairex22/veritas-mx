// Identificador de sesión de chat por navegador y por negocio (no requiere
// cuenta). Solo vive en localStorage de la persona visitante.
function randomId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function getSessionId(businessSlug: string): string {
  const key = `cf_session_${businessSlug}`;
  let id = localStorage.getItem(key);
  if (!id) {
    id = randomId();
    localStorage.setItem(key, id);
  }
  return id;
}

export function newIdempotencyKey(): string {
  return randomId();
}
