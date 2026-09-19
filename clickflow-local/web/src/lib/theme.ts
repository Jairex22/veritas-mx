import type { BusinessColors } from "./types";

// Aplica la identidad del negocio (colores) sobre los tokens base, sin
// tocar el CSS. Si el negocio no definió colores propios, se quedan los de
// ClickFlow Local (marfil / grafito / verde petróleo / coral).
export function applyBusinessTheme(colors: BusinessColors | null | undefined) {
  const root = document.documentElement.style;
  if (!colors) return;
  if (colors.ivory) root.setProperty("--cf-bg", colors.ivory);
  if (colors.graphite) {
    root.setProperty("--cf-text", colors.graphite);
    root.setProperty("--cf-accent-text", colors.graphite);
  }
  if (colors.petrol) {
    root.setProperty("--cf-primary", colors.petrol);
  }
  if (colors.coral) {
    root.setProperty("--cf-accent", colors.coral);
  }
}
