export interface BusinessColors {
  ivory: string;
  graphite: string;
  petrol: string;
  coral: string;
}

export interface PublicBusiness {
  slug: string;
  name: string;
  description: string;
  logoUrl: string | null;
  colors: BusinessColors;
  address: string | null;
  mapsUrl: string | null;
  timezone: string;
  weeklySchedule: string;
  scheduleExceptions: string;
  openNow: boolean;
  openStatusText: string;
  whatsappAvailable: boolean;
  contactEmail: string | null;
  contactPhone: string | null;
  aiConfigured: boolean;
  aiPaused: boolean;
  isDemo: boolean;
}

export interface CatalogVariant {
  name: string;
  priceCents: number;
  durationMinutes?: number;
}

export interface CatalogItemPublic {
  id: string;
  category: string;
  name: string;
  description: string;
  priceCents: number;
  priceFormatted: string;
  isPromo: boolean;
  durationMinutes: number | null;
  variants: CatalogVariant[];
  imageUrl: string | null;
}

export interface QuoteLine {
  itemId: string;
  name: string;
  variantName: string | null;
  quantity: number;
  unitPriceCents: number;
  lineTotalCents: number;
  isPromo: boolean;
}

export interface QuoteResult {
  ok: boolean;
  lines: QuoteLine[];
  totalCents: number;
  totalFormatted: string;
  errors: string[];
}

export type RequestStatus =
  | "borrador"
  | "solicitud_recibida"
  | "pendiente_confirmacion"
  | "confirmada"
  | "cancelada";

export interface ServiceRequest {
  id: string;
  businessId: string;
  conversationId: string | null;
  type: "order" | "appointment" | "contact";
  folio: string;
  status: RequestStatus;
  payload: Record<string, unknown>;
  totalCents: number | null;
  idempotencyKey: string;
  notes: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ChatProposal {
  proposalType: "order" | "appointment" | "contact";
  ok: boolean;
  errors: string[];
  [key: string]: unknown;
}

export interface ChatResponse {
  reply: string;
  aiConfigured: boolean;
  proposal: ChatProposal | null;
  error?: boolean;
  conversationId: string;
}

export interface ChatMessageVM {
  id: string;
  role: "user" | "assistant";
  content: string;
  proposal?: ChatProposal | null;
}
