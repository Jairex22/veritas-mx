import type { Business } from "../types.js";
import { findItemsByKeyword, formatMoneyMXN, effectivePriceCents } from "../services/catalogService.js";
import { getOpenStatus, formatWeeklySchedule } from "../services/hoursService.js";
import { getBusinessHours, listFaqs } from "../db/repo.js";
import type { ChatTurnResult } from "./agent.js";

// Motor determinista de respaldo: se usa SOLO cuando no hay credencial de IA
// configurada (OPENAI_API_KEY). No pretende ser una conversación libre real;
// resuelve lo que puede verificarse con datos reales del negocio (catálogo,
// horario, FAQs) y siempre deja claro que la IA conversacional está
// pendiente de configurar, además de ofrecer las acciones rápidas de la
// interfaz para catálogo, citas y contacto, que no dependen de la IA.

function normalize(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .trim();
}

const GREETING_WORDS = ["hola", "buenas", "buenos dias", "buenas tardes", "buenas noches", "que tal"];
const PRICE_WORDS = ["precio", "cuanto cuesta", "cuesta", "vale", "catalogo", "productos", "servicios", "menu"];
const HOURS_WORDS = ["horario", "abren", "cierran", "hora abren", "a que hora"];
const CONTACT_WORDS = ["hablar con alguien", "persona real", "humano", "asesor", "whatsapp"];

export function runFallbackEngine(
  business: Business,
  _history: { role: "user" | "assistant"; content: string }[],
  userMessage: string
): ChatTurnResult {
  const disclaimer =
    "(La conversación libre con inteligencia artificial está pendiente de configurar para este negocio; te ayudo con lo básico usando su información real.) ";
  const q = normalize(userMessage);

  if (GREETING_WORDS.some((w) => q.includes(w)) || q.length < 3) {
    return {
      reply: `${disclaimer}¡Hola! Soy el asistente de ${business.name}. Puedo ayudarte a ver precios, encontrar un producto o servicio, o dejar tu solicitud de cita o contacto. ¿Qué te gustaría hacer?`,
      aiConfigured: false,
      proposal: null,
      error: false,
    };
  }

  if (HOURS_WORDS.some((w) => q.includes(w))) {
    const status = getOpenStatus(business);
    const hours = getBusinessHours(business.id);
    return {
      reply: `${status.hoursText}\nHorario completo: ${formatWeeklySchedule(hours)}`,
      aiConfigured: false,
      proposal: null,
      error: false,
    };
  }

  if (CONTACT_WORDS.some((w) => q.includes(w))) {
    return {
      reply:
        "Puedo dejar registrada tu solicitud para que el negocio te contacte. Usa el botón 'Hablar con el negocio' para confirmarlo, o cuéntame brevemente el motivo.",
      aiConfigured: false,
      proposal: { proposalType: "contact", ok: true, errors: [], reason: userMessage.slice(0, 300) },
      error: false,
    };
  }

  if (PRICE_WORDS.some((w) => q.includes(w)) || true) {
    const matches = findItemsByKeyword(business.id, userMessage).slice(0, 3);
    if (matches.length > 0) {
      const lines = matches.map((item) => {
        const price = effectivePriceCents(item);
        return `• ${item.name}: ${formatMoneyMXN(price.priceCents)}${price.isPromo ? " (promoción vigente)" : ""}`;
      });
      return {
        reply: `${disclaimer}Esto encontré en el catálogo:\n${lines.join("\n")}\n¿Quieres que prepare un pedido o una cita con alguno de estos?`,
        aiConfigured: false,
        proposal: null,
        error: false,
      };
    }
  }

  const faqs = listFaqs(business.id, true);
  const faqMatch = faqs.find((f) => normalize(f.question).includes(q) || q.includes(normalize(f.question).slice(0, 12)));
  if (faqMatch) {
    return { reply: faqMatch.answer, aiConfigured: false, proposal: null, error: false };
  }

  return {
    reply: `${disclaimer}No logré identificar bien tu mensaje. Puedes usar los botones de 'Ver precios', 'Encontrar un servicio', 'Solicitar cita' o 'Hablar con el negocio', o intenta describir lo que buscas con otras palabras.`,
    aiConfigured: false,
    proposal: null,
    error: false,
  };
}
