import type { Business, BusinessHourException, BusinessHours } from "../types.js";
import { getBusinessHours, getHourExceptions } from "../db/repo.js";

export interface OpenStatus {
  isOpen: boolean;
  reason: "open" | "closed_today" | "outside_hours" | "exception" | "no_schedule";
  todayLabel: string;
  hoursText: string;
}

function localPartsInTimezone(timezone: string, date = new Date()) {
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  const parts = Object.fromEntries(fmt.formatToParts(date).map((p) => [p.type, p.value]));
  const weekdayMap: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  return {
    dayOfWeek: weekdayMap[parts.weekday] ?? 0,
    hhmm: `${parts.hour}:${parts.minute}`,
    isoDate: `${parts.year}-${parts.month}-${parts.day}`,
  };
}

const DAY_NAMES_ES = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];

export function getOpenStatus(business: Business): OpenStatus {
  const hours = getBusinessHours(business.id);
  const exceptions = getHourExceptions(business.id);
  const { dayOfWeek, hhmm, isoDate } = localPartsInTimezone(business.timezone);
  const todayLabel = DAY_NAMES_ES[dayOfWeek];

  const exception = exceptions.find((e) => e.date === isoDate);
  if (exception) {
    if (exception.closed) {
      return { isOpen: false, reason: "exception", todayLabel, hoursText: exception.note || "Cerrado hoy por horario especial." };
    }
    if (exception.opens && exception.closes) {
      const isOpen = hhmm >= exception.opens && hhmm <= exception.closes;
      return {
        isOpen,
        reason: isOpen ? "open" : "outside_hours",
        todayLabel,
        hoursText: `Hoy (horario especial): ${exception.opens} - ${exception.closes}`,
      };
    }
  }

  if (hours.length === 0) {
    return { isOpen: false, reason: "no_schedule", todayLabel, hoursText: "El negocio no ha configurado su horario todavía." };
  }

  const today = hours.find((h) => h.dayOfWeek === dayOfWeek);
  if (!today || today.closed) {
    return { isOpen: false, reason: "closed_today", todayLabel, hoursText: `Hoy (${todayLabel}) el negocio no abre.` };
  }

  const isOpen = hhmm >= today.opens && hhmm <= today.closes;
  return {
    isOpen,
    reason: isOpen ? "open" : "outside_hours",
    todayLabel,
    hoursText: `Hoy (${todayLabel}): ${today.opens} - ${today.closes}`,
  };
}

export function formatWeeklySchedule(hours: BusinessHours[]): string {
  if (hours.length === 0) return "Horario no configurado.";
  const sorted = [...hours].sort((a, b) => a.dayOfWeek - b.dayOfWeek);
  return sorted
    .map((h) => `${DAY_NAMES_ES[h.dayOfWeek]}: ${h.closed ? "cerrado" : `${h.opens} - ${h.closes}`}`)
    .join(" · ");
}

export function formatExceptions(exceptions: BusinessHourException[]): string {
  if (exceptions.length === 0) return "Sin excepciones de horario registradas.";
  return exceptions
    .map((e) => `${e.date}: ${e.closed ? `cerrado${e.note ? ` (${e.note})` : ""}` : `${e.opens} - ${e.closes}`}`)
    .join(" · ");
}
