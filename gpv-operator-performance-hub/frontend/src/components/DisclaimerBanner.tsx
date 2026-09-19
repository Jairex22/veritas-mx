import { Info } from "lucide-react";

export default function DisclaimerBanner({ text }: { text?: string }) {
  return (
    <div className="disclaimer-banner">
      <Info size={16} color="var(--color-steel-blue)" style={{ flexShrink: 0, marginTop: 2 }} />
      <span>
        {text ??
          "Este indicador es una herramienta de apoyo para mejora continua. Debe revisarse junto con el contexto operativo antes de tomar decisiones."}
      </span>
    </div>
  );
}
