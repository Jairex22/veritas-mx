import { Router } from "express";
import { z } from "zod";
import {
  addMessage,
  countMessagesToday,
  getBusinessHours,
  getHourExceptions,
  getOrCreateConversation,
  listFaqs,
  listMessages,
  logUnansweredQuestion,
  touchConversation,
} from "../db/repo.js";
import { getPublicCatalog, effectivePriceCents, formatMoneyMXN } from "../services/catalogService.js";
import { calculateQuote } from "../services/quoteService.js";
import { buildAppointmentProposal, buildOrderProposal, createRequestIdempotent } from "../services/requestService.js";
import { getOpenStatus, formatWeeklySchedule, formatExceptions } from "../services/hoursService.js";
import { runChatTurn } from "../ai/agent.js";
import { isAiConfigured } from "../ai/openaiClient.js";
import { chatLimiter, MAX_MESSAGES_PER_CONVERSATION_PER_DAY } from "../middleware/rateLimit.js";
import { logger } from "../utils/logger.js";

export const publicRouter = Router({ mergeParams: true });

// ---------- Información pública del negocio ----------

publicRouter.get("/", (req, res) => {
  const business = req.business!;
  const hours = getBusinessHours(business.id);
  const exceptions = getHourExceptions(business.id);
  const status = getOpenStatus(business);
  res.json({
    slug: business.slug,
    name: business.name,
    description: business.description,
    logoUrl: business.logoUrl,
    colors: business.colors,
    address: business.address,
    mapsUrl: business.mapsUrl,
    timezone: business.timezone,
    weeklySchedule: formatWeeklySchedule(hours),
    scheduleExceptions: formatExceptions(exceptions),
    openNow: status.isOpen,
    openStatusText: status.hoursText,
    whatsappAvailable: !!business.whatsappNumber,
    contactEmail: business.contactEmail,
    contactPhone: business.contactPhone,
    aiConfigured: isAiConfigured(),
    aiPaused: business.aiPaused,
    isDemo: business.isDemo,
  });
});

publicRouter.get("/catalog", (req, res) => {
  const business = req.business!;
  const query = typeof req.query.query === "string" ? req.query.query : "";
  const items = getPublicCatalog(business.id)
    .filter((item) => {
      if (!query) return true;
      const q = query.toLowerCase();
      return (
        item.name.toLowerCase().includes(q) ||
        item.category.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q)
      );
    })
    .map((item) => {
      const price = effectivePriceCents(item);
      return {
        id: item.id,
        category: item.category,
        name: item.name,
        description: item.description,
        priceCents: price.priceCents,
        priceFormatted: formatMoneyMXN(price.priceCents),
        isPromo: price.isPromo,
        durationMinutes: item.durationMinutes,
        variants: item.variants,
        imageUrl: item.imageUrl,
      };
    });
  res.json({ items });
});

publicRouter.get("/faqs", (req, res) => {
  const business = req.business!;
  res.json({ faqs: listFaqs(business.id, true).map((f) => ({ question: f.question, answer: f.answer })) });
});

// ---------- Cotización (determinista, sin IA) ----------

const quoteSchema = z.object({
  lines: z
    .array(
      z.object({
        itemId: z.string(),
        variantName: z.string().optional(),
        quantity: z.number().int().positive().max(50).optional(),
      })
    )
    .min(1)
    .max(20),
});

publicRouter.post("/quote", (req, res) => {
  const parsed = quoteSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ error: "Datos de cotización inválidos." });
  }
  const business = req.business!;
  const quote = calculateQuote(business.id, parsed.data.lines);
  res.json(quote);
});

// ---------- Chat ----------

const chatSchema = z.object({
  sessionId: z.string().min(6).max(128),
  message: z.string().min(1).max(2000),
});

publicRouter.post("/chat", chatLimiter, async (req, res) => {
  const parsed = chatSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ error: "Mensaje inválido." });
  }
  const business = req.business!;
  const { sessionId, message } = parsed.data;

  const conversation = getOrCreateConversation(business.id, sessionId, "widget");
  touchConversation(conversation.id);

  if (countMessagesToday(conversation.id) >= MAX_MESSAGES_PER_CONVERSATION_PER_DAY) {
    return res.status(429).json({
      error: "Se alcanzó el límite de mensajes por hoy para esta conversación. Intenta mañana o contacta al negocio.",
    });
  }

  if (conversation.humanPausedUntil && new Date(conversation.humanPausedUntil) > new Date()) {
    addMessage(conversation.id, "user", message);
    return res.json({
      reply:
        "Una persona del negocio está atendiendo esta conversación directamente. Las respuestas automáticas están pausadas por ahora.",
      aiConfigured: isAiConfigured(),
      proposal: null,
      conversationId: conversation.id,
    });
  }

  addMessage(conversation.id, "user", message);
  const history = listMessages(conversation.id, 40)
    .slice(0, -1)
    .map((m) => ({ role: m.role as "user" | "assistant", content: m.content }))
    .filter((m) => m.role === "user" || m.role === "assistant");

  try {
    const result = await runChatTurn({ business, history, userMessage: message });
    addMessage(conversation.id, "assistant", result.reply);
    if (!result.aiConfigured || result.error) {
      logUnansweredQuestion(business.id, conversation.id, message);
    }
    res.json({ ...result, conversationId: conversation.id });
  } catch (err) {
    logger.error("chat_route_failed", { businessId: business.id });
    res.status(200).json({
      reply:
        "No pudimos procesar tu mensaje en este momento. Intenta de nuevo o usa el botón para hablar con el negocio.",
      aiConfigured: isAiConfigured(),
      proposal: null,
      error: true,
      conversationId: conversation.id,
    });
  }
});

// ---------- Solicitudes (creación real, con confirmación e idempotencia) ----------

const orderRequestSchema = z.object({
  sessionId: z.string().min(6).max(128),
  idempotencyKey: z.string().min(10).max(128),
  lines: z
    .array(
      z.object({
        itemId: z.string(),
        variantName: z.string().optional(),
        quantity: z.number().int().positive().max(50).optional(),
      })
    )
    .min(1)
    .max(20),
  deliveryPreference: z.string().max(200).optional(),
  customerNote: z.string().max(1000).optional(),
});

publicRouter.post("/requests/order", (req, res) => {
  const parsed = orderRequestSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Datos de pedido inválidos." });
  const business = req.business!;
  const data = parsed.data;

  const proposal = buildOrderProposal(business.id, data.lines);
  if (!proposal.ok) {
    return res.status(422).json({ error: "No se pudo validar el pedido.", details: proposal.errors });
  }
  const conversation = getOrCreateConversation(business.id, data.sessionId, "widget");
  const { request, wasExisting } = createRequestIdempotent({
    businessId: business.id,
    conversationId: conversation.id,
    type: "order",
    payload: {
      lines: proposal.lines,
      deliveryPreference: data.deliveryPreference ?? null,
      customerNote: data.customerNote ?? null,
    },
    totalCents: proposal.totalCents,
    idempotencyKey: data.idempotencyKey,
  });
  res.status(wasExisting ? 200 : 201).json({ request, wasExisting });
});

const appointmentRequestSchema = z.object({
  sessionId: z.string().min(6).max(128),
  idempotencyKey: z.string().min(10).max(128),
  itemId: z.string(),
  preferredDate: z.string(),
  preferredTime: z.string(),
  customerNote: z.string().max(1000).optional(),
});

publicRouter.post("/requests/appointment", (req, res) => {
  const parsed = appointmentRequestSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Datos de cita inválidos." });
  const business = req.business!;
  const data = parsed.data;

  const proposal = buildAppointmentProposal(business.id, data);
  if (!proposal.ok) {
    return res.status(422).json({ error: "No se pudo validar la cita.", details: proposal.errors });
  }
  const conversation = getOrCreateConversation(business.id, data.sessionId, "widget");
  const { request, wasExisting } = createRequestIdempotent({
    businessId: business.id,
    conversationId: conversation.id,
    type: "appointment",
    payload: {
      itemId: data.itemId,
      itemName: proposal.itemName,
      preferredDate: data.preferredDate,
      preferredTime: data.preferredTime,
      customerNote: data.customerNote ?? null,
      warnings: proposal.warnings,
    },
    totalCents: proposal.priceCents,
    idempotencyKey: data.idempotencyKey,
  });
  res.status(wasExisting ? 200 : 201).json({ request, wasExisting, warnings: proposal.warnings });
});

const contactRequestSchema = z.object({
  sessionId: z.string().min(6).max(128),
  idempotencyKey: z.string().min(10).max(128),
  reason: z.string().min(1).max(1000),
  contactName: z.string().max(200).optional(),
  contactPhone: z.string().max(50).optional(),
});

publicRouter.post("/requests/contact", (req, res) => {
  const parsed = contactRequestSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Datos de contacto inválidos." });
  const business = req.business!;
  const data = parsed.data;
  const conversation = getOrCreateConversation(business.id, data.sessionId, "widget");
  const { request, wasExisting } = createRequestIdempotent({
    businessId: business.id,
    conversationId: conversation.id,
    type: "contact",
    payload: {
      reason: data.reason,
      contactName: data.contactName ?? null,
      contactPhone: data.contactPhone ?? null,
    },
    totalCents: null,
    idempotencyKey: data.idempotencyKey,
  });
  res.status(wasExisting ? 200 : 201).json({ request, wasExisting });
});
