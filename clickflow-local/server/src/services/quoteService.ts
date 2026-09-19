import { getCatalogItem } from "../db/repo.js";
import { effectivePriceCents, formatMoneyMXN } from "./catalogService.js";

export interface QuoteLineInput {
  itemId: string;
  variantName?: string;
  quantity?: number;
}

export interface QuoteLineResult {
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
  lines: QuoteLineResult[];
  totalCents: number;
  totalFormatted: string;
  errors: string[];
}

// Toda la aritmética de precios vive aquí, en código de servidor, usando
// exclusivamente datos de la base de datos. El modelo de IA jamás produce
// el total final: solo puede pedir esta herramienta.
export function calculateQuote(businessId: string, lines: QuoteLineInput[]): QuoteResult {
  const errors: string[] = [];
  const results: QuoteLineResult[] = [];

  for (const line of lines) {
    const item = getCatalogItem(businessId, line.itemId);
    if (!item || !item.active) {
      errors.push(`El artículo solicitado (${line.itemId}) ya no está disponible en el catálogo.`);
      continue;
    }
    const quantity = Math.max(1, Math.floor(line.quantity ?? 1));
    let unitPriceCents = effectivePriceCents(item).priceCents;
    const isPromo = effectivePriceCents(item).isPromo;
    let variantName: string | null = null;

    if (line.variantName) {
      const variant = item.variants.find(
        (v) => v.name.toLowerCase() === line.variantName!.toLowerCase()
      );
      if (!variant) {
        errors.push(`La variante "${line.variantName}" no existe para "${item.name}".`);
        continue;
      }
      unitPriceCents = variant.priceCents;
      variantName = variant.name;
    }

    results.push({
      itemId: item.id,
      name: item.name,
      variantName,
      quantity,
      unitPriceCents,
      lineTotalCents: unitPriceCents * quantity,
      isPromo,
    });
  }

  const totalCents = results.reduce((sum, r) => sum + r.lineTotalCents, 0);
  return {
    ok: errors.length === 0 && results.length > 0,
    lines: results,
    totalCents,
    totalFormatted: formatMoneyMXN(totalCents),
    errors,
  };
}
