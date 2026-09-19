import { useState, type ReactNode } from "react";
import { Info } from "lucide-react";

export default function Tooltip({ text, children }: { text: string; children?: ReactNode }) {
  const [visible, setVisible] = useState(false);
  return (
    <span
      className="tooltip-wrap"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
      tabIndex={0}
      role="button"
      aria-label={text}
    >
      {children ?? <Info size={13} color="var(--text-muted)" />}
      {visible && <span className="tooltip-bubble" role="tooltip">{text}</span>}
    </span>
  );
}
