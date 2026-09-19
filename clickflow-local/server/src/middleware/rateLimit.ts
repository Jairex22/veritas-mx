import rateLimit from "express-rate-limit";

// Límite general contra abuso en endpoints públicos (por IP).
export const publicApiLimiter = rateLimit({
  windowMs: 60 * 1000,
  limit: 60,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: "Demasiadas solicitudes. Espera un momento e intenta de nuevo." },
});

// Límite más estricto específicamente para el chat, que es lo más costoso
// (llamadas al proveedor de IA). Limita por IP; el límite por sesión de
// conversación se aplica además dentro de la ruta de chat.
export const chatLimiter = rateLimit({
  windowMs: 60 * 1000,
  limit: 20,
  standardHeaders: true,
  legacyHeaders: false,
  message: {
    error: "Estás enviando mensajes muy rápido. Espera unos segundos antes de continuar.",
  },
});

export const adminAuthLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  limit: 20,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: "Demasiados intentos. Intenta de nuevo en unos minutos." },
});

export const MAX_MESSAGES_PER_CONVERSATION_PER_DAY = 60;
