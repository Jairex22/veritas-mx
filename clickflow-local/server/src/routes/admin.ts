import { Router } from "express";
import bcrypt from "bcryptjs";
import { z } from "zod";
import { requireAdminAuth, signAdminToken } from "../middleware/auth.js";
import { adminAuthLimiter } from "../middleware/rateLimit.js";
import {
  addHourException,
  deleteCatalogItem,
  deleteHourException,
  deleteFaq,
  getAdminByEmail,
  getAiUsageSummary,
  getBusinessById,
  getBusinessBySlug,
  getBusinessHours,
  getHourExceptions,
  getMetrics,
  insertCatalogItem,
  insertFaq,
  listCatalog,
  listConversations,
  listFaqs,
  listMessages,
  listRequests,
  listUnansweredQuestions,
  markUnansweredResolved,
  pauseConversationForHuman,
  replaceBusinessHours,
  setAiPaused,
  updateBusiness,
  updateCatalogItem,
  updateFaq,
} from "../db/repo.js";
import { transitionRequestStatus, canTransition } from "../services/requestService.js";
import type { RequestStatus } from "../types.js";

export const adminRouter = Router();

// ---------- Autenticación ----------

const loginSchema = z.object({
  businessSlug: z.string(),
  email: z.string().email(),
  password: z.string().min(1),
});

adminRouter.post("/login", adminAuthLimiter, (req, res) => {
  const parsed = loginSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Datos de acceso inválidos." });
  const { businessSlug, email, password } = parsed.data;

  const resolvedBusiness = getBusinessBySlug(businessSlug);
  if (!resolvedBusiness) return res.status(401).json({ error: "Credenciales inválidas." });

  const admin = getAdminByEmail(resolvedBusiness.id, email);
  if (!admin || !bcrypt.compareSync(password, admin.passwordHash)) {
    return res.status(401).json({ error: "Credenciales inválidas." });
  }
  const token = signAdminToken({ adminId: admin.id, businessId: admin.businessId, role: admin.role });
  res.json({
    token,
    business: { id: resolvedBusiness.id, slug: resolvedBusiness.slug, name: resolvedBusiness.name },
  });
});

adminRouter.use(requireAdminAuth);

function currentBusiness(req: import("express").Request) {
  return getBusinessById(req.admin!.businessId)!;
}

// ---------- Negocio ----------

adminRouter.get("/me", (req, res) => {
  const business = currentBusiness(req);
  res.json({
    business,
    hours: getBusinessHours(business.id),
    exceptions: getHourExceptions(business.id),
  });
});

const businessUpdateSchema = z.object({
  name: z.string().min(1).max(200).optional(),
  description: z.string().max(2000).optional(),
  logoUrl: z.string().url().nullable().optional(),
  colors: z
    .object({ ivory: z.string(), graphite: z.string(), petrol: z.string(), coral: z.string() })
    .optional(),
  address: z.string().max(400).nullable().optional(),
  mapsUrl: z.string().url().nullable().optional(),
  timezone: z.string().optional(),
  whatsappNumber: z.string().max(30).nullable().optional(),
  contactEmail: z.string().email().nullable().optional(),
  contactPhone: z.string().max(30).nullable().optional(),
  humanHandoffNotes: z.array(z.object({ trigger: z.string(), note: z.string() })).optional(),
  policies: z
    .object({
      delivery: z.string().max(2000).optional(),
      cancellation: z.string().max(2000).optional(),
      changes: z.string().max(2000).optional(),
    })
    .optional(),
  retentionDays: z.number().int().min(1).max(3650).optional(),
});

adminRouter.put("/business", (req, res) => {
  const parsed = businessUpdateSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Datos inválidos.", details: parsed.error.flatten() });
  const business = updateBusiness(req.admin!.businessId, parsed.data as any);
  res.json({ business });
});

const hoursSchema = z.array(
  z.object({
    dayOfWeek: z.number().int().min(0).max(6),
    opens: z.string(),
    closes: z.string(),
    closed: z.boolean(),
  })
);

adminRouter.put("/business/hours", (req, res) => {
  const parsed = hoursSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Horario inválido." });
  replaceBusinessHours(req.admin!.businessId, parsed.data);
  res.json({ hours: getBusinessHours(req.admin!.businessId) });
});

const exceptionSchema = z.object({
  date: z.string(),
  closed: z.boolean(),
  opens: z.string().optional(),
  closes: z.string().optional(),
  note: z.string().max(300).optional(),
});

adminRouter.post("/business/hours/exceptions", (req, res) => {
  const parsed = exceptionSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Excepción inválida." });
  addHourException(req.admin!.businessId, parsed.data);
  res.json({ exceptions: getHourExceptions(req.admin!.businessId) });
});

adminRouter.delete("/business/hours/exceptions/:date", (req, res) => {
  deleteHourException(req.admin!.businessId, req.params.date);
  res.json({ exceptions: getHourExceptions(req.admin!.businessId) });
});

adminRouter.post("/business/pause-ai", (req, res) => {
  const paused = !!req.body?.paused;
  setAiPaused(req.admin!.businessId, paused);
  res.json({ aiPaused: paused });
});

// ---------- Catálogo ----------

adminRouter.get("/catalog", (req, res) => {
  res.json({ items: listCatalog(req.admin!.businessId) });
});

const catalogItemSchema = z.object({
  category: z.string().min(1).max(100),
  name: z.string().min(1).max(200),
  description: z.string().max(2000).default(""),
  priceCents: z.number().int().min(0),
  durationMinutes: z.number().int().min(0).nullable().optional(),
  variants: z
    .array(z.object({ name: z.string(), priceCents: z.number().int().min(0), durationMinutes: z.number().int().min(0).optional() }))
    .default([]),
  imageUrl: z.string().url().nullable().optional(),
  active: z.boolean().default(true),
  promo: z
    .object({ priceCents: z.number().int().min(0), startsAt: z.string(), endsAt: z.string(), label: z.string().optional() })
    .nullable()
    .optional(),
});

adminRouter.post("/catalog", (req, res) => {
  const parsed = catalogItemSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Artículo inválido.", details: parsed.error.flatten() });
  const item = insertCatalogItem({ businessId: req.admin!.businessId, ...parsed.data, promo: parsed.data.promo ?? null, durationMinutes: parsed.data.durationMinutes ?? null, imageUrl: parsed.data.imageUrl ?? null } as any);
  res.status(201).json({ item });
});

adminRouter.put("/catalog/:id", (req, res) => {
  const parsed = catalogItemSchema.partial().safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Artículo inválido.", details: parsed.error.flatten() });
  const item = updateCatalogItem(req.admin!.businessId, req.params.id, parsed.data as any);
  if (!item) return res.status(404).json({ error: "No encontrado." });
  res.json({ item });
});

adminRouter.delete("/catalog/:id", (req, res) => {
  deleteCatalogItem(req.admin!.businessId, req.params.id);
  res.json({ ok: true });
});

// ---------- FAQs ----------

adminRouter.get("/faqs", (req, res) => {
  res.json({ faqs: listFaqs(req.admin!.businessId) });
});

const faqSchema = z.object({ question: z.string().min(1).max(500), answer: z.string().min(1).max(3000), active: z.boolean().default(true) });

adminRouter.post("/faqs", (req, res) => {
  const parsed = faqSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "FAQ inválida." });
  const faq = insertFaq({ businessId: req.admin!.businessId, ...parsed.data });
  res.status(201).json({ faq });
});

adminRouter.put("/faqs/:id", (req, res) => {
  const parsed = faqSchema.partial().safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "FAQ inválida." });
  updateFaq(req.admin!.businessId, req.params.id, parsed.data);
  res.json({ ok: true });
});

adminRouter.delete("/faqs/:id", (req, res) => {
  deleteFaq(req.admin!.businessId, req.params.id);
  res.json({ ok: true });
});

// ---------- Solicitudes ----------

adminRouter.get("/requests", (req, res) => {
  const status = req.query.status as RequestStatus | undefined;
  const type = req.query.type as any;
  res.json({ requests: listRequests(req.admin!.businessId, { status, type }) });
});

const statusSchema = z.object({
  status: z.enum(["borrador", "solicitud_recibida", "pendiente_confirmacion", "confirmada", "cancelada"]),
  notes: z.string().max(1000).optional(),
});

adminRouter.post("/requests/:id/status", (req, res) => {
  const parsed = statusSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Estado inválido." });
  const requests = listRequests(req.admin!.businessId);
  const current = requests.find((r) => r.id === req.params.id);
  if (!current) return res.status(404).json({ error: "Solicitud no encontrada." });
  if (!canTransition(current.status, parsed.data.status) && current.status !== parsed.data.status) {
    return res.status(409).json({ error: `No se puede pasar de "${current.status}" a "${parsed.data.status}".` });
  }
  const result = transitionRequestStatus(req.admin!.businessId, req.params.id, parsed.data.status, parsed.data.notes);
  if (!result.ok) return res.status(404).json({ error: "Solicitud no encontrada." });
  res.json({ request: result.request });
});

// ---------- Conversaciones ----------

adminRouter.get("/conversations", (req, res) => {
  res.json({ conversations: listConversations(req.admin!.businessId) });
});

adminRouter.get("/conversations/:id/messages", (req, res) => {
  const conversations = listConversations(req.admin!.businessId, 500);
  const conv = conversations.find((c) => c.id === req.params.id);
  if (!conv) return res.status(404).json({ error: "Conversación no encontrada." });
  res.json({ messages: listMessages(conv.id, 200) });
});

const pauseHumanSchema = z.object({ minutes: z.number().int().min(1).max(24 * 60).default(60) });

adminRouter.post("/conversations/:id/pause-for-human", (req, res) => {
  const conversations = listConversations(req.admin!.businessId, 500);
  const conv = conversations.find((c) => c.id === req.params.id);
  if (!conv) return res.status(404).json({ error: "Conversación no encontrada." });
  const parsed = pauseHumanSchema.safeParse(req.body);
  const minutes = parsed.success ? parsed.data.minutes : 60;
  const until = new Date(Date.now() + minutes * 60_000).toISOString();
  pauseConversationForHuman(conv.id, until);
  res.json({ humanPausedUntil: until });
});

// ---------- Preguntas sin responder ----------

adminRouter.get("/unanswered-questions", (req, res) => {
  res.json({ questions: listUnansweredQuestions(req.admin!.businessId) });
});

adminRouter.post("/unanswered-questions/:id/resolve", (req, res) => {
  markUnansweredResolved(req.admin!.businessId, req.params.id);
  res.json({ ok: true });
});

// ---------- Métricas y consumo de IA ----------

adminRouter.get("/metrics", (req, res) => {
  res.json(getMetrics(req.admin!.businessId));
});

adminRouter.get("/ai-usage", (req, res) => {
  res.json({ usage: getAiUsageSummary(req.admin!.businessId) });
});
