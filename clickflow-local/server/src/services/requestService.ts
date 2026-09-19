import { generateFolio } from "../utils/folio.js";
import {
  findRequestByIdempotencyKey,
  getCatalogItem,
  insertRequest,
  updateRequestStatus,
} from "../db/repo.js";
import type { RequestStatus, RequestType, ServiceRequest } from "../types.js";
import { calculateQuote, type QuoteLineInput } from "./quoteService.js";
import { getOpenStatus } from "./hoursService.js";
import { getBusinessById } from "../db/repo.js";

export interface OrderProposal {
  ok: boolean;
  errors: string[];
  lines: ReturnType<typeof calculateQuote>["lines"];
  totalCents: number;
  totalFormatted: string;
}

export function buildOrderProposal(businessId: string, lines: QuoteLineInput[]): OrderProposal {
  const quote = calculateQuote(businessId, lines);
  return {
    ok: quote.ok,
    errors: quote.errors,
    lines: quote.lines,
    totalCents: quote.totalCents,
    totalFormatted: quote.totalFormatted,
  };
}

export interface AppointmentProposalInput {
  itemId: string;
  preferredDate: string; // YYYY-MM-DD
  preferredTime: string; // HH:MM
  notes?: string;
}

export interface AppointmentProposal {
  ok: boolean;
  errors: string[];
  warnings: string[];
  itemName: string;
  durationMinutes: number | null;
  priceCents: number;
  priceFormatted: string;
  preferredDate: string;
  preferredTime: string;
}

export function buildAppointmentProposal(
  businessId: string,
  input: AppointmentProposalInput
): AppointmentProposal {
  const errors: string[] = [];
  const warnings: string[] = [];
  const item = getCatalogItem(businessId, input.itemId);
  if (!item || !item.active) {
    errors.push("El servicio solicitado ya no está disponible.");
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(input.preferredDate)) {
    errors.push("La fecha debe tener formato AAAA-MM-DD.");
  }
  if (!/^\d{2}:\d{2}$/.test(input.preferredTime)) {
    errors.push("La hora debe tener formato HH:MM.");
  }
  const business = getBusinessById(businessId);
  if (business) {
    const status = getOpenStatus(business);
    if (!status.isOpen) {
      warnings.push(
        "La hora u horario que eliges está fuera del horario habitual del negocio; el negocio revisará tu solicitud y te confirmará disponibilidad."
      );
    }
  }
  const quote = item ? calculateQuote(businessId, [{ itemId: item.id }]) : null;
  return {
    ok: errors.length === 0,
    errors,
    warnings,
    itemName: item?.name ?? "(no disponible)",
    durationMinutes: item?.durationMinutes ?? null,
    priceCents: quote?.totalCents ?? 0,
    priceFormatted: quote?.totalFormatted ?? "$0.00",
    preferredDate: input.preferredDate,
    preferredTime: input.preferredTime,
  };
}

export interface CreateRequestInput {
  businessId: string;
  conversationId: string | null;
  type: RequestType;
  payload: Record<string, unknown>;
  totalCents: number | null;
  idempotencyKey: string;
}

const INITIAL_STATUS: Record<RequestType, RequestStatus> = {
  order: "solicitud_recibida",
  // No hay agenda conectada en esta versión: una cita nunca nace "confirmada".
  appointment: "pendiente_confirmacion",
  contact: "solicitud_recibida",
};

export function createRequestIdempotent(input: CreateRequestInput): {
  request: ServiceRequest;
  wasExisting: boolean;
} {
  const existing = findRequestByIdempotencyKey(input.businessId, input.idempotencyKey);
  if (existing) {
    return { request: existing, wasExisting: true };
  }
  const folio = generateFolio(input.type);
  const request = insertRequest({
    businessId: input.businessId,
    conversationId: input.conversationId,
    type: input.type,
    folio,
    status: INITIAL_STATUS[input.type],
    payload: input.payload,
    totalCents: input.totalCents,
    idempotencyKey: input.idempotencyKey,
  });
  return { request, wasExisting: false };
}

const VALID_TRANSITIONS: Record<RequestStatus, RequestStatus[]> = {
  borrador: ["solicitud_recibida", "cancelada"],
  solicitud_recibida: ["pendiente_confirmacion", "confirmada", "cancelada"],
  pendiente_confirmacion: ["confirmada", "cancelada"],
  confirmada: ["cancelada"],
  cancelada: [],
};

export function transitionRequestStatus(
  businessId: string,
  id: string,
  nextStatus: RequestStatus,
  notes?: string
): { ok: true; request: ServiceRequest } | { ok: false; error: string } {
  const current = updateRequestStatus(businessId, id, nextStatus, notes);
  if (!current) return { ok: false, error: "not_found" };
  return { ok: true, request: current };
}

export function canTransition(from: RequestStatus, to: RequestStatus): boolean {
  return VALID_TRANSITIONS[from]?.includes(to) ?? false;
}
