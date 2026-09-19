import { nanoid } from "nanoid";
import { db, nowIso } from "./db.js";
import type {
  AdminUser,
  Business,
  BusinessHourException,
  BusinessHours,
  CatalogItem,
  Conversation,
  Faq,
  Message,
  RequestStatus,
  RequestType,
  ServiceRequest,
  UnansweredQuestion,
} from "../types.js";

// ---------- Mappers ----------

function rowToBusiness(row: any): Business {
  return {
    id: row.id,
    slug: row.slug,
    name: row.name,
    description: row.description,
    logoUrl: row.logo_url,
    colors: JSON.parse(row.colors_json),
    address: row.address,
    mapsUrl: row.maps_url,
    timezone: row.timezone,
    whatsappNumber: row.whatsapp_number,
    contactEmail: row.contact_email,
    contactPhone: row.contact_phone,
    humanHandoffNotes: JSON.parse(row.human_handoff_json ?? "[]"),
    policies: JSON.parse(row.policies_json ?? "{}"),
    aiEnabled: !!row.ai_enabled,
    aiPaused: !!row.ai_paused,
    aiModel: row.ai_model,
    isDemo: !!row.is_demo,
    retentionDays: row.retention_days,
    createdAt: row.created_at,
  };
}

function rowToCatalogItem(row: any): CatalogItem {
  return {
    id: row.id,
    businessId: row.business_id,
    category: row.category,
    name: row.name,
    description: row.description,
    priceCents: row.price_cents,
    durationMinutes: row.duration_minutes,
    variants: JSON.parse(row.variants_json ?? "[]"),
    imageUrl: row.image_url,
    active: !!row.active,
    promo: row.promo_json ? JSON.parse(row.promo_json) : null,
  };
}

function rowToFaq(row: any): Faq {
  return {
    id: row.id,
    businessId: row.business_id,
    question: row.question,
    answer: row.answer,
    active: !!row.active,
  };
}

function rowToRequest(row: any): ServiceRequest {
  return {
    id: row.id,
    businessId: row.business_id,
    conversationId: row.conversation_id,
    type: row.type,
    folio: row.folio,
    status: row.status,
    payload: JSON.parse(row.payload_json ?? "{}"),
    totalCents: row.total_cents,
    idempotencyKey: row.idempotency_key,
    notes: row.notes,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

function rowToConversation(row: any): Conversation {
  return {
    id: row.id,
    businessId: row.business_id,
    sessionId: row.session_id,
    channel: row.channel,
    createdAt: row.created_at,
    lastActivityAt: row.last_activity_at,
    humanPausedUntil: row.human_paused_until,
  };
}

function rowToMessage(row: any): Message {
  return {
    id: row.id,
    conversationId: row.conversation_id,
    role: row.role,
    content: row.content,
    createdAt: row.created_at,
  };
}

// ---------- Business ----------

export function getBusinessBySlug(slug: string): Business | null {
  const row = db.prepare("SELECT * FROM businesses WHERE slug = ?").get(slug);
  return row ? rowToBusiness(row) : null;
}

export function getBusinessById(id: string): Business | null {
  const row = db.prepare("SELECT * FROM businesses WHERE id = ?").get(id);
  return row ? rowToBusiness(row) : null;
}

export function listBusinesses(): Business[] {
  const rows = db.prepare("SELECT * FROM businesses ORDER BY created_at ASC").all();
  return rows.map(rowToBusiness);
}

export function insertBusiness(input: Omit<Business, "id" | "createdAt">): Business {
  const id = nanoid();
  const createdAt = nowIso();
  db.prepare(
    `INSERT INTO businesses (id, slug, name, description, logo_url, colors_json, address, maps_url,
      timezone, whatsapp_number, contact_email, contact_phone, human_handoff_json, policies_json,
      ai_enabled, ai_paused, ai_model, is_demo, retention_days, created_at)
     VALUES (@id, @slug, @name, @description, @logoUrl, @colorsJson, @address, @mapsUrl,
      @timezone, @whatsappNumber, @contactEmail, @contactPhone, @humanHandoffJson, @policiesJson,
      @aiEnabled, @aiPaused, @aiModel, @isDemo, @retentionDays, @createdAt)`
  ).run({
    id,
    slug: input.slug,
    name: input.name,
    description: input.description,
    logoUrl: input.logoUrl,
    colorsJson: JSON.stringify(input.colors),
    address: input.address,
    mapsUrl: input.mapsUrl,
    timezone: input.timezone,
    whatsappNumber: input.whatsappNumber,
    contactEmail: input.contactEmail,
    contactPhone: input.contactPhone,
    humanHandoffJson: JSON.stringify(input.humanHandoffNotes),
    policiesJson: JSON.stringify(input.policies),
    aiEnabled: input.aiEnabled ? 1 : 0,
    aiPaused: input.aiPaused ? 1 : 0,
    aiModel: input.aiModel,
    isDemo: input.isDemo ? 1 : 0,
    retentionDays: input.retentionDays,
    createdAt,
  });
  return getBusinessById(id)!;
}

export function updateBusiness(id: string, patch: Partial<Business>): Business | null {
  const current = getBusinessById(id);
  if (!current) return null;
  const merged: Business = { ...current, ...patch };
  db.prepare(
    `UPDATE businesses SET name=@name, description=@description, logo_url=@logoUrl,
      colors_json=@colorsJson, address=@address, maps_url=@mapsUrl, timezone=@timezone,
      whatsapp_number=@whatsappNumber, contact_email=@contactEmail, contact_phone=@contactPhone,
      human_handoff_json=@humanHandoffJson, policies_json=@policiesJson, ai_enabled=@aiEnabled,
      ai_paused=@aiPaused, ai_model=@aiModel, retention_days=@retentionDays
     WHERE id=@id`
  ).run({
    id,
    name: merged.name,
    description: merged.description,
    logoUrl: merged.logoUrl,
    colorsJson: JSON.stringify(merged.colors),
    address: merged.address,
    mapsUrl: merged.mapsUrl,
    timezone: merged.timezone,
    whatsappNumber: merged.whatsappNumber,
    contactEmail: merged.contactEmail,
    contactPhone: merged.contactPhone,
    humanHandoffJson: JSON.stringify(merged.humanHandoffNotes),
    policiesJson: JSON.stringify(merged.policies),
    aiEnabled: merged.aiEnabled ? 1 : 0,
    aiPaused: merged.aiPaused ? 1 : 0,
    aiModel: merged.aiModel,
    retentionDays: merged.retentionDays,
  });
  return getBusinessById(id);
}

export function setAiPaused(businessId: string, paused: boolean): void {
  db.prepare("UPDATE businesses SET ai_paused = ? WHERE id = ?").run(paused ? 1 : 0, businessId);
}

// ---------- Hours ----------

export function getBusinessHours(businessId: string): BusinessHours[] {
  const rows = db
    .prepare("SELECT * FROM business_hours WHERE business_id = ? ORDER BY day_of_week ASC")
    .all(businessId) as any[];
  return rows.map((r) => ({
    dayOfWeek: r.day_of_week,
    opens: r.opens,
    closes: r.closes,
    closed: !!r.closed,
  }));
}

export function replaceBusinessHours(businessId: string, hours: BusinessHours[]): void {
  const tx = db.transaction(() => {
    db.prepare("DELETE FROM business_hours WHERE business_id = ?").run(businessId);
    const stmt = db.prepare(
      "INSERT INTO business_hours (id, business_id, day_of_week, opens, closes, closed) VALUES (?, ?, ?, ?, ?, ?)"
    );
    for (const h of hours) {
      stmt.run(nanoid(), businessId, h.dayOfWeek, h.opens, h.closes, h.closed ? 1 : 0);
    }
  });
  tx();
}

export function getHourExceptions(businessId: string): BusinessHourException[] {
  const rows = db
    .prepare("SELECT * FROM business_hour_exceptions WHERE business_id = ? ORDER BY date ASC")
    .all(businessId) as any[];
  return rows.map((r) => ({
    date: r.date,
    closed: !!r.closed,
    opens: r.opens ?? undefined,
    closes: r.closes ?? undefined,
    note: r.note ?? undefined,
  }));
}

export function addHourException(businessId: string, ex: BusinessHourException): void {
  db.prepare(
    "INSERT INTO business_hour_exceptions (id, business_id, date, closed, opens, closes, note) VALUES (?, ?, ?, ?, ?, ?, ?)"
  ).run(nanoid(), businessId, ex.date, ex.closed ? 1 : 0, ex.opens ?? null, ex.closes ?? null, ex.note ?? null);
}

export function deleteHourException(businessId: string, date: string): void {
  db.prepare("DELETE FROM business_hour_exceptions WHERE business_id = ? AND date = ?").run(businessId, date);
}

// ---------- Catalog ----------

export function listCatalog(businessId: string, onlyActive = false): CatalogItem[] {
  const sql = onlyActive
    ? "SELECT * FROM catalog_items WHERE business_id = ? AND active = 1 ORDER BY category, name"
    : "SELECT * FROM catalog_items WHERE business_id = ? ORDER BY category, name";
  const rows = db.prepare(sql).all(businessId) as any[];
  return rows.map(rowToCatalogItem);
}

export function getCatalogItem(businessId: string, id: string): CatalogItem | null {
  const row = db
    .prepare("SELECT * FROM catalog_items WHERE business_id = ? AND id = ?")
    .get(businessId, id);
  return row ? rowToCatalogItem(row as any) : null;
}

export function insertCatalogItem(item: Omit<CatalogItem, "id">): CatalogItem {
  const id = nanoid();
  db.prepare(
    `INSERT INTO catalog_items (id, business_id, category, name, description, price_cents,
      duration_minutes, variants_json, image_url, active, promo_json)
     VALUES (@id, @businessId, @category, @name, @description, @priceCents,
      @durationMinutes, @variantsJson, @imageUrl, @active, @promoJson)`
  ).run({
    id,
    businessId: item.businessId,
    category: item.category,
    name: item.name,
    description: item.description,
    priceCents: item.priceCents,
    durationMinutes: item.durationMinutes,
    variantsJson: JSON.stringify(item.variants ?? []),
    imageUrl: item.imageUrl,
    active: item.active ? 1 : 0,
    promoJson: item.promo ? JSON.stringify(item.promo) : null,
  });
  return getCatalogItem(item.businessId, id)!;
}

export function updateCatalogItem(
  businessId: string,
  id: string,
  patch: Partial<CatalogItem>
): CatalogItem | null {
  const current = getCatalogItem(businessId, id);
  if (!current) return null;
  const merged = { ...current, ...patch };
  db.prepare(
    `UPDATE catalog_items SET category=@category, name=@name, description=@description,
      price_cents=@priceCents, duration_minutes=@durationMinutes, variants_json=@variantsJson,
      image_url=@imageUrl, active=@active, promo_json=@promoJson
     WHERE business_id=@businessId AND id=@id`
  ).run({
    id,
    businessId,
    category: merged.category,
    name: merged.name,
    description: merged.description,
    priceCents: merged.priceCents,
    durationMinutes: merged.durationMinutes,
    variantsJson: JSON.stringify(merged.variants ?? []),
    imageUrl: merged.imageUrl,
    active: merged.active ? 1 : 0,
    promoJson: merged.promo ? JSON.stringify(merged.promo) : null,
  });
  return getCatalogItem(businessId, id);
}

export function deleteCatalogItem(businessId: string, id: string): void {
  db.prepare("DELETE FROM catalog_items WHERE business_id = ? AND id = ?").run(businessId, id);
}

// ---------- FAQs ----------

export function listFaqs(businessId: string, onlyActive = false): Faq[] {
  const sql = onlyActive
    ? "SELECT * FROM faqs WHERE business_id = ? AND active = 1"
    : "SELECT * FROM faqs WHERE business_id = ?";
  const rows = db.prepare(sql).all(businessId) as any[];
  return rows.map(rowToFaq);
}

export function insertFaq(faq: Omit<Faq, "id">): Faq {
  const id = nanoid();
  db.prepare(
    "INSERT INTO faqs (id, business_id, question, answer, active) VALUES (?, ?, ?, ?, ?)"
  ).run(id, faq.businessId, faq.question, faq.answer, faq.active ? 1 : 0);
  return { ...faq, id };
}

export function updateFaq(businessId: string, id: string, patch: Partial<Faq>): void {
  const rows = listFaqs(businessId);
  const current = rows.find((f) => f.id === id);
  if (!current) return;
  const merged = { ...current, ...patch };
  db.prepare(
    "UPDATE faqs SET question=?, answer=?, active=? WHERE business_id=? AND id=?"
  ).run(merged.question, merged.answer, merged.active ? 1 : 0, businessId, id);
}

export function deleteFaq(businessId: string, id: string): void {
  db.prepare("DELETE FROM faqs WHERE business_id = ? AND id = ?").run(businessId, id);
}

// ---------- Admin users ----------

export function getAdminByEmail(businessId: string, email: string): AdminUser | null {
  const row = db
    .prepare("SELECT * FROM admin_users WHERE business_id = ? AND email = ?")
    .get(businessId, email.toLowerCase());
  if (!row) return null;
  const r = row as any;
  return { id: r.id, businessId: r.business_id, email: r.email, passwordHash: r.password_hash, role: r.role };
}

export function getAdminByEmailAnyBusiness(email: string): AdminUser | null {
  const row = db.prepare("SELECT * FROM admin_users WHERE email = ?").get(email.toLowerCase());
  if (!row) return null;
  const r = row as any;
  return { id: r.id, businessId: r.business_id, email: r.email, passwordHash: r.password_hash, role: r.role };
}

export function insertAdminUser(user: Omit<AdminUser, "id">): AdminUser {
  const id = nanoid();
  db.prepare(
    "INSERT INTO admin_users (id, business_id, email, password_hash, role) VALUES (?, ?, ?, ?, ?)"
  ).run(id, user.businessId, user.email.toLowerCase(), user.passwordHash, user.role);
  return { ...user, id, email: user.email.toLowerCase() };
}

// ---------- Conversations & messages ----------

export function getOrCreateConversation(
  businessId: string,
  sessionId: string,
  channel: string
): Conversation {
  const existing = db
    .prepare("SELECT * FROM conversations WHERE business_id = ? AND session_id = ?")
    .get(businessId, sessionId);
  if (existing) return rowToConversation(existing);
  const id = nanoid();
  const ts = nowIso();
  db.prepare(
    "INSERT INTO conversations (id, business_id, session_id, channel, created_at, last_activity_at) VALUES (?, ?, ?, ?, ?, ?)"
  ).run(id, businessId, sessionId, channel, ts, ts);
  return getOrCreateConversation(businessId, sessionId, channel);
}

export function touchConversation(id: string): void {
  db.prepare("UPDATE conversations SET last_activity_at = ? WHERE id = ?").run(nowIso(), id);
}

export function pauseConversationForHuman(id: string, untilIso: string): void {
  db.prepare("UPDATE conversations SET human_paused_until = ? WHERE id = ?").run(untilIso, id);
}

export function getConversation(businessId: string, id: string): Conversation | null {
  const row = db
    .prepare("SELECT * FROM conversations WHERE business_id = ? AND id = ?")
    .get(businessId, id);
  return row ? rowToConversation(row as any) : null;
}

export function listConversations(businessId: string, limit = 100): Conversation[] {
  const rows = db
    .prepare(
      "SELECT * FROM conversations WHERE business_id = ? ORDER BY last_activity_at DESC LIMIT ?"
    )
    .all(businessId, limit) as any[];
  return rows.map(rowToConversation);
}

export function addMessage(conversationId: string, role: Message["role"], content: string): Message {
  const id = nanoid();
  const createdAt = nowIso();
  db.prepare(
    "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)"
  ).run(id, conversationId, role, content, createdAt);
  return { id, conversationId, role, content, createdAt };
}

export function listMessages(conversationId: string, limit = 30): Message[] {
  const rows = db
    .prepare(
      "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT ?"
    )
    .all(conversationId, limit) as any[];
  return rows.map(rowToMessage);
}

export function countMessagesToday(conversationId: string): number {
  const row = db
    .prepare(
      "SELECT COUNT(*) as c FROM messages WHERE conversation_id = ? AND role = 'user' AND date(created_at) = date('now')"
    )
    .get(conversationId) as any;
  return row?.c ?? 0;
}

// ---------- Requests ----------

export function findRequestByIdempotencyKey(
  businessId: string,
  idempotencyKey: string
): ServiceRequest | null {
  const row = db
    .prepare("SELECT * FROM requests WHERE business_id = ? AND idempotency_key = ?")
    .get(businessId, idempotencyKey);
  return row ? rowToRequest(row as any) : null;
}

export function insertRequest(input: {
  businessId: string;
  conversationId: string | null;
  type: RequestType;
  folio: string;
  status: RequestStatus;
  payload: Record<string, unknown>;
  totalCents: number | null;
  idempotencyKey: string;
}): ServiceRequest {
  const id = nanoid();
  const ts = nowIso();
  db.prepare(
    `INSERT INTO requests (id, business_id, conversation_id, type, folio, status, payload_json,
      total_cents, idempotency_key, created_at, updated_at)
     VALUES (@id, @businessId, @conversationId, @type, @folio, @status, @payloadJson,
      @totalCents, @idempotencyKey, @createdAt, @updatedAt)`
  ).run({
    id,
    businessId: input.businessId,
    conversationId: input.conversationId,
    type: input.type,
    folio: input.folio,
    status: input.status,
    payloadJson: JSON.stringify(input.payload),
    totalCents: input.totalCents,
    idempotencyKey: input.idempotencyKey,
    createdAt: ts,
    updatedAt: ts,
  });
  return rowToRequest(
    db.prepare("SELECT * FROM requests WHERE id = ?").get(id)
  );
}

export function listRequests(
  businessId: string,
  filter?: { status?: RequestStatus; type?: RequestType }
): ServiceRequest[] {
  let sql = "SELECT * FROM requests WHERE business_id = ?";
  const params: unknown[] = [businessId];
  if (filter?.status) {
    sql += " AND status = ?";
    params.push(filter.status);
  }
  if (filter?.type) {
    sql += " AND type = ?";
    params.push(filter.type);
  }
  sql += " ORDER BY created_at DESC";
  const rows = db.prepare(sql).all(...params) as any[];
  return rows.map(rowToRequest);
}

export function getRequest(businessId: string, id: string): ServiceRequest | null {
  const row = db
    .prepare("SELECT * FROM requests WHERE business_id = ? AND id = ?")
    .get(businessId, id);
  return row ? rowToRequest(row as any) : null;
}

export function updateRequestStatus(
  businessId: string,
  id: string,
  status: RequestStatus,
  notes?: string
): ServiceRequest | null {
  const current = getRequest(businessId, id);
  if (!current) return null;
  db.prepare(
    "UPDATE requests SET status = ?, notes = COALESCE(?, notes), updated_at = ? WHERE id = ? AND business_id = ?"
  ).run(status, notes ?? null, nowIso(), id, businessId);
  return getRequest(businessId, id);
}

// ---------- Unanswered questions ----------

export function logUnansweredQuestion(
  businessId: string,
  conversationId: string | null,
  question: string
): UnansweredQuestion {
  const id = nanoid();
  const createdAt = nowIso();
  db.prepare(
    "INSERT INTO unanswered_questions (id, business_id, conversation_id, question, created_at, resolved) VALUES (?, ?, ?, ?, ?, 0)"
  ).run(id, businessId, conversationId, question, createdAt);
  return { id, businessId, conversationId, question, createdAt, resolved: false };
}

export function listUnansweredQuestions(businessId: string): UnansweredQuestion[] {
  const rows = db
    .prepare(
      "SELECT * FROM unanswered_questions WHERE business_id = ? ORDER BY created_at DESC"
    )
    .all(businessId) as any[];
  return rows.map((r) => ({
    id: r.id,
    businessId: r.business_id,
    conversationId: r.conversation_id,
    question: r.question,
    createdAt: r.created_at,
    resolved: !!r.resolved,
  }));
}

export function markUnansweredResolved(businessId: string, id: string): void {
  db.prepare(
    "UPDATE unanswered_questions SET resolved = 1 WHERE business_id = ? AND id = ?"
  ).run(businessId, id);
}

// ---------- AI usage ----------

export function recordAiUsage(businessId: string, tokensIn: number, tokensOut: number): void {
  const today = new Date().toISOString().slice(0, 10);
  db.prepare(
    `INSERT INTO ai_usage (business_id, date, tokens_in, tokens_out, requests_count)
     VALUES (?, ?, ?, ?, 1)
     ON CONFLICT(business_id, date) DO UPDATE SET
       tokens_in = tokens_in + excluded.tokens_in,
       tokens_out = tokens_out + excluded.tokens_out,
       requests_count = requests_count + 1`
  ).run(businessId, today, tokensIn, tokensOut);
}

export function getAiUsageSummary(businessId: string, days = 30) {
  const rows = db
    .prepare(
      `SELECT * FROM ai_usage WHERE business_id = ? AND date >= date('now', ?) ORDER BY date ASC`
    )
    .all(businessId, `-${days} days`) as any[];
  return rows.map((r) => ({
    date: r.date,
    tokensIn: r.tokens_in,
    tokensOut: r.tokens_out,
    requestsCount: r.requests_count,
  }));
}

// ---------- Metrics ----------

export function getMetrics(businessId: string) {
  const conversations = db
    .prepare("SELECT COUNT(*) as c FROM conversations WHERE business_id = ?")
    .get(businessId) as any;
  const requestsTotal = db
    .prepare("SELECT COUNT(*) as c FROM requests WHERE business_id = ?")
    .get(businessId) as any;
  const contactsRequested = db
    .prepare("SELECT COUNT(*) as c FROM requests WHERE business_id = ? AND type = 'contact'")
    .get(businessId) as any;
  const byStatus = db
    .prepare("SELECT status, COUNT(*) as c FROM requests WHERE business_id = ? GROUP BY status")
    .all(businessId) as any[];
  return {
    conversations: conversations?.c ?? 0,
    requestsTotal: requestsTotal?.c ?? 0,
    contactsRequested: contactsRequested?.c ?? 0,
    requestsByStatus: Object.fromEntries(byStatus.map((r) => [r.status, r.c])),
  };
}
