// Tipos compartidos del backend de ClickFlow Local.

export type RequestType = "order" | "appointment" | "contact";

export type RequestStatus =
  | "borrador"
  | "solicitud_recibida"
  | "pendiente_confirmacion"
  | "confirmada"
  | "cancelada";

export interface BusinessColors {
  ivory: string;
  graphite: string;
  petrol: string;
  coral: string;
}

export interface BusinessHours {
  dayOfWeek: number; // 0 = domingo ... 6 = sábado
  opens: string; // "09:00"
  closes: string; // "19:00"
  closed: boolean;
}

export interface BusinessHourException {
  date: string; // "2026-12-25"
  closed: boolean;
  opens?: string;
  closes?: string;
  note?: string;
}

export interface BusinessPolicies {
  delivery?: string;
  cancellation?: string;
  changes?: string;
}

export interface HumanHandoffRule {
  trigger: string;
  note: string;
}

export interface Business {
  id: string;
  slug: string;
  name: string;
  description: string;
  logoUrl: string | null;
  colors: BusinessColors;
  address: string | null;
  mapsUrl: string | null;
  timezone: string;
  whatsappNumber: string | null;
  contactEmail: string | null;
  contactPhone: string | null;
  humanHandoffNotes: HumanHandoffRule[];
  policies: BusinessPolicies;
  aiEnabled: boolean;
  aiPaused: boolean;
  aiModel: string;
  isDemo: boolean;
  retentionDays: number;
  createdAt: string;
}

export interface CatalogItemVariant {
  name: string;
  priceCents: number;
  durationMinutes?: number;
}

export interface CatalogItemPromo {
  priceCents: number;
  startsAt: string;
  endsAt: string;
  label?: string;
}

export interface CatalogItem {
  id: string;
  businessId: string;
  category: string;
  name: string;
  description: string;
  priceCents: number;
  durationMinutes: number | null;
  variants: CatalogItemVariant[];
  imageUrl: string | null;
  active: boolean;
  promo: CatalogItemPromo | null;
}

export interface Faq {
  id: string;
  businessId: string;
  question: string;
  answer: string;
  active: boolean;
}

export interface AdminUser {
  id: string;
  businessId: string;
  email: string;
  passwordHash: string;
  role: "owner" | "staff";
}

export interface Conversation {
  id: string;
  businessId: string;
  sessionId: string;
  channel: string;
  createdAt: string;
  lastActivityAt: string;
  humanPausedUntil: string | null;
}

export interface Message {
  id: string;
  conversationId: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  createdAt: string;
}

export interface ServiceRequest {
  id: string;
  businessId: string;
  conversationId: string | null;
  type: RequestType;
  folio: string;
  status: RequestStatus;
  payload: Record<string, unknown>;
  totalCents: number | null;
  idempotencyKey: string;
  notes: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface UnansweredQuestion {
  id: string;
  businessId: string;
  conversationId: string | null;
  question: string;
  createdAt: string;
  resolved: boolean;
}

export interface AiUsageRow {
  businessId: string;
  date: string;
  tokensIn: number;
  tokensOut: number;
  requestsCount: number;
}
