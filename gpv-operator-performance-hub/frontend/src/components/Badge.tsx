import { classificationToTone } from "../lib/format";

const TONE_CLASS: Record<string, string> = {
  excellent: "badge--excellent",
  good: "badge--good",
  warning: "badge--warning",
  bad: "badge--bad",
  neutral: "badge--neutral",
};

export default function Badge({ classification }: { classification: string }) {
  const tone = classificationToTone(classification);
  return <span className={`badge ${TONE_CLASS[tone]}`}>{classification}</span>;
}
