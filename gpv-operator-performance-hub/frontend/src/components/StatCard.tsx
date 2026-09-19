import { ArrowUp, ArrowDown, Minus } from "lucide-react";
import Tooltip from "./Tooltip";
import styles from "./StatCard.module.css";
import type { KpiValue } from "../lib/types";

const TONE_CLASS: Record<string, string> = {
  good: styles.toneGood,
  warning: styles.toneWarning,
  bad: styles.toneBad,
  neutral: styles.toneNeutral,
};

const TREND_ICON = { up: ArrowUp, down: ArrowDown, neutral: Minus };

export default function StatCard({ kpi, tooltip }: { kpi: KpiValue; tooltip?: string }) {
  const TrendIcon = TREND_ICON[kpi.trend_direction];
  return (
    <div className={`panel ${styles.card}`}>
      <div className={styles.accent} data-tone={kpi.tone} />
      <div className={styles.body}>
        <div className={styles.labelRow}>
          <span className={styles.label}>{kpi.label}</span>
          {tooltip && <Tooltip text={tooltip} />}
        </div>
        <div className={styles.valueRow}>
          <span className={styles.value}>{kpi.value}</span>
          <span className={`${styles.trendPill} ${TONE_CLASS[kpi.tone]}`}>
            <TrendIcon size={12} />
          </span>
        </div>
        <p className={styles.context}>{kpi.context}</p>
      </div>
    </div>
  );
}
