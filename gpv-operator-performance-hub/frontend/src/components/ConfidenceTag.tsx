import Tooltip from "./Tooltip";

const TONE: Record<string, string> = {
  Alta: "badge--good",
  "Media-alta": "badge--good",
  Media: "badge--warning",
  "Media-baja": "badge--warning",
  Baja: "badge--bad",
};

export default function ConfidenceTag({ level, sampleSize }: { level: string; sampleSize?: number }) {
  return (
    <span className="tooltip-wrap">
      <span className={`badge ${TONE[level] ?? "badge--neutral"}`}>Confianza: {level}</span>
      {sampleSize !== undefined && (
        <Tooltip
          text={`Calculado con ${sampleSize} unidades. A mayor número de unidades y días distintos, mayor confianza en el resultado.`}
        />
      )}
    </span>
  );
}
