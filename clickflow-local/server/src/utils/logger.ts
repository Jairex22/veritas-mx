// Logger mínimo: nunca registra claves, contraseñas ni contenido de mensajes de clientes.
type Level = "info" | "warn" | "error";

function emit(level: Level, message: string, meta?: Record<string, unknown>) {
  const safeMeta = meta ? redact(meta) : undefined;
  const line = {
    ts: new Date().toISOString(),
    level,
    message,
    ...(safeMeta ?? {}),
  };
  // eslint-disable-next-line no-console
  console[level === "info" ? "log" : level](JSON.stringify(line));
}

const SENSITIVE_KEYS = new Set([
  "password",
  "passwordHash",
  "apiKey",
  "authorization",
  "token",
  "openaiApiKey",
]);

function redact(obj: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    out[key] = SENSITIVE_KEYS.has(key) ? "[redacted]" : value;
  }
  return out;
}

export const logger = {
  info: (message: string, meta?: Record<string, unknown>) => emit("info", message, meta),
  warn: (message: string, meta?: Record<string, unknown>) => emit("warn", message, meta),
  error: (message: string, meta?: Record<string, unknown>) => emit("error", message, meta),
};
