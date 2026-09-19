import type { Business } from "../types.js";
import {
  getBusinessHours,
  getHourExceptions,
  listFaqs,
} from "../db/repo.js";
import { findItemsByKeyword, findItemsWithinBudget, formatMoneyMXN, getPublicCatalog, effectivePriceCents } from "../services/catalogService.js";
import { calculateQuote } from "../services/quoteService.js";
import { buildAppointmentProposal, buildOrderProposal } from "../services/requestService.js";
import { formatExceptions, formatWeeklySchedule, getOpenStatus } from "../services/hoursService.js";

// Definiciones de herramientas en formato de la Responses API de OpenAI
// (tools de tipo "function"). El modelo SOLO puede proponer estas llamadas;
// toda la lógica (precios, disponibilidad, validación) vive en el servidor,
// en las funciones "run" de abajo. Ninguna herramienta escribe en la tabla
// de solicitudes: crear una solicitud real ocurre por un endpoint aparte,
// después de que la persona confirma explícitamente el resumen en la
// interfaz (ver routes/requests.ts).

export const toolDefinitions = [
  {
    type: "function" as const,
    name: "get_business_info",
    description:
      "Obtiene información confiable del negocio: descripción, dirección, horario vigente, políticas de entrega/cancelación/cambios y datos de contacto. Úsala antes de responder cualquier pregunta sobre el negocio.",
    parameters: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    type: "function" as const,
    name: "search_catalog",
    description:
      "Busca productos o servicios activos en el catálogo real del negocio por palabra clave y/o presupuesto máximo. Devuelve hasta 5 resultados con precio vigente. Nunca inventes artículos o precios: usa siempre esta herramienta.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "Palabra clave o necesidad del cliente, en español." },
        maxPriceCents: {
          type: "integer",
          description: "Presupuesto máximo en centavos de peso mexicano (MXN), si el cliente lo indicó.",
        },
      },
      required: [],
      additionalProperties: false,
    },
  },
  {
    type: "function" as const,
    name: "get_faqs",
    description: "Devuelve las preguntas frecuentes configuradas por el negocio, opcionalmente filtradas por palabra clave.",
    parameters: {
      type: "object",
      properties: { query: { type: "string" } },
      required: [],
      additionalProperties: false,
    },
  },
  {
    type: "function" as const,
    name: "calculate_quote",
    description:
      "Calcula el total exacto (usando precios reales de la base de datos) de una lista de artículos/servicios con cantidad y variante opcional. Úsala siempre antes de mencionar un total; el resultado no es negociable ni puede modificarse por el cliente.",
    parameters: {
      type: "object",
      properties: {
        lines: {
          type: "array",
          items: {
            type: "object",
            properties: {
              itemId: { type: "string" },
              variantName: { type: "string" },
              quantity: { type: "integer", minimum: 1 },
            },
            required: ["itemId"],
            additionalProperties: false,
          },
        },
      },
      required: ["lines"],
      additionalProperties: false,
    },
  },
  {
    type: "function" as const,
    name: "propose_order_request",
    description:
      "Prepara (sin guardar todavía) una propuesta de pedido para mostrarle a la persona un resumen editable. La persona debe confirmar explícitamente en la interfaz antes de que se registre de verdad.",
    parameters: {
      type: "object",
      properties: {
        lines: {
          type: "array",
          items: {
            type: "object",
            properties: {
              itemId: { type: "string" },
              variantName: { type: "string" },
              quantity: { type: "integer", minimum: 1 },
            },
            required: ["itemId"],
            additionalProperties: false,
          },
        },
        deliveryPreference: { type: "string", description: "Ej. 'recoger en tienda' o 'a domicilio', si aplica." },
        customerNote: { type: "string" },
      },
      required: ["lines"],
      additionalProperties: false,
    },
  },
  {
    type: "function" as const,
    name: "propose_appointment_request",
    description:
      "Prepara (sin guardar todavía) una propuesta de cita para un servicio, fecha y hora preferidas. La persona debe confirmar explícitamente en la interfaz. Esto NO reserva la hora: el negocio confirmará disponibilidad después.",
    parameters: {
      type: "object",
      properties: {
        itemId: { type: "string" },
        preferredDate: { type: "string", description: "Formato AAAA-MM-DD" },
        preferredTime: { type: "string", description: "Formato HH:MM, 24 horas" },
        customerNote: { type: "string" },
      },
      required: ["itemId", "preferredDate", "preferredTime"],
      additionalProperties: false,
    },
  },
  {
    type: "function" as const,
    name: "propose_contact_request",
    description:
      "Prepara (sin guardar todavía) una solicitud para que una persona del negocio contacte al cliente, cuando el asistente no puede resolver algo o el cliente lo pide explícitamente.",
    parameters: {
      type: "object",
      properties: {
        reason: { type: "string", description: "Motivo breve de la solicitud de contacto." },
      },
      required: ["reason"],
      additionalProperties: false,
    },
  },
] as const;

export type ToolName = (typeof toolDefinitions)[number]["name"];

export function runTool(business: Business, name: string, args: Record<string, unknown>): unknown {
  switch (name) {
    case "get_business_info": {
      const hours = getBusinessHours(business.id);
      const exceptions = getHourExceptions(business.id);
      const openStatus = getOpenStatus(business);
      return {
        name: business.name,
        description: business.description,
        address: business.address,
        timezone: business.timezone,
        weeklySchedule: formatWeeklySchedule(hours),
        scheduleExceptions: formatExceptions(exceptions),
        openNow: openStatus.isOpen,
        openStatusText: openStatus.hoursText,
        policies: business.policies,
        contactEmail: business.contactEmail,
        contactPhone: business.contactPhone,
        whatsappAvailable: !!business.whatsappNumber,
      };
    }
    case "search_catalog": {
      const query = typeof args.query === "string" ? args.query : "";
      const maxPriceCents = typeof args.maxPriceCents === "number" ? args.maxPriceCents : undefined;
      const items = maxPriceCents
        ? findItemsWithinBudget(business.id, maxPriceCents, query)
        : findItemsByKeyword(business.id, query);
      const top = items.slice(0, 5).map((item) => {
        const price = effectivePriceCents(item);
        return {
          itemId: item.id,
          name: item.name,
          category: item.category,
          description: item.description,
          priceCents: price.priceCents,
          priceFormatted: formatMoneyMXN(price.priceCents),
          isPromo: price.isPromo,
          durationMinutes: item.durationMinutes,
          variants: item.variants,
          imageUrl: item.imageUrl,
        };
      });
      return { count: top.length, items: top, totalActiveItems: getPublicCatalog(business.id).length };
    }
    case "get_faqs": {
      const query = typeof args.query === "string" ? args.query.toLowerCase() : "";
      const faqs = listFaqs(business.id, true).filter(
        (f) =>
          !query ||
          f.question.toLowerCase().includes(query) ||
          f.answer.toLowerCase().includes(query)
      );
      return { faqs: faqs.map((f) => ({ question: f.question, answer: f.answer })) };
    }
    case "calculate_quote": {
      const lines = Array.isArray(args.lines) ? (args.lines as any[]) : [];
      return calculateQuote(business.id, lines);
    }
    case "propose_order_request": {
      const lines = Array.isArray(args.lines) ? (args.lines as any[]) : [];
      const proposal = buildOrderProposal(business.id, lines);
      return {
        ...proposal,
        proposalType: "order",
        deliveryPreference: typeof args.deliveryPreference === "string" ? args.deliveryPreference : null,
        customerNote: typeof args.customerNote === "string" ? args.customerNote : null,
      };
    }
    case "propose_appointment_request": {
      const proposal = buildAppointmentProposal(business.id, {
        itemId: String(args.itemId ?? ""),
        preferredDate: String(args.preferredDate ?? ""),
        preferredTime: String(args.preferredTime ?? ""),
        notes: typeof args.customerNote === "string" ? args.customerNote : undefined,
      });
      return {
        ...proposal,
        proposalType: "appointment",
        itemId: args.itemId,
        customerNote: typeof args.customerNote === "string" ? args.customerNote : null,
      };
    }
    case "propose_contact_request": {
      return {
        proposalType: "contact",
        ok: true,
        errors: [],
        reason: typeof args.reason === "string" ? args.reason : "El cliente solicitó hablar con el negocio.",
      };
    }
    default:
      return { error: `Herramienta desconocida: ${name}` };
  }
}
