import type { CatalogItem } from "../types.js";
import { getCatalogItem, listCatalog } from "../db/repo.js";

// Precio vigente de un artículo: si hay una promoción activa (dentro de su
// vigencia), se usa; si no, el precio base. Esta es la ÚNICA fuente de verdad
// de precios — el modelo de IA nunca calcula ni inventa montos.
export function effectivePriceCents(item: CatalogItem, atIso: string = new Date().toISOString()): {
  priceCents: number;
  isPromo: boolean;
  promoLabel?: string;
} {
  if (item.promo) {
    const now = new Date(atIso).getTime();
    const start = new Date(item.promo.startsAt).getTime();
    const end = new Date(item.promo.endsAt).getTime();
    if (now >= start && now <= end) {
      return { priceCents: item.promo.priceCents, isPromo: true, promoLabel: item.promo.label };
    }
  }
  return { priceCents: item.priceCents, isPromo: false };
}

export function getPublicCatalog(businessId: string): CatalogItem[] {
  return listCatalog(businessId, true);
}

export function findItemsByKeyword(businessId: string, keyword: string): CatalogItem[] {
  const items = listCatalog(businessId, true);
  const q = normalize(keyword);
  if (!q) return items;
  return items.filter((item) => {
    const haystack = normalize(`${item.name} ${item.category} ${item.description}`);
    return haystack.includes(q) || q.split(" ").some((word) => word.length > 2 && haystack.includes(word));
  });
}

export function findItemsWithinBudget(businessId: string, maxCents: number, keyword?: string): CatalogItem[] {
  const pool = keyword ? findItemsByKeyword(businessId, keyword) : listCatalog(businessId, true);
  return pool
    .filter((item) => effectivePriceCents(item).priceCents <= maxCents)
    .sort((a, b) => effectivePriceCents(a).priceCents - effectivePriceCents(b).priceCents);
}

export function requireCatalogItem(businessId: string, itemId: string): CatalogItem | null {
  return getCatalogItem(businessId, itemId);
}

function normalize(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .trim();
}

export function formatMoneyMXN(cents: number): string {
  return (cents / 100).toLocaleString("es-MX", { style: "currency", currency: "MXN" });
}
