import type { ReactNode } from "react";

interface Props {
  value: number;
  max: number;
  size?: number;
  stroke?: number;
  children?: ReactNode;
}

export default function Ring({ value, max, size = 176, stroke = 14, children }: Props) {
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  const fraction = max > 0 ? Math.min(value / max, 1) : 0;
  const c = size / 2;
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <defs>
          <linearGradient id="ring-gradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#86efac" />
            <stop offset="1" stopColor="#22c55e" />
          </linearGradient>
        </defs>
        <circle cx={c} cy={c} r={r} className="ring-track" strokeWidth={stroke} fill="none" />
        <circle
          cx={c}
          cy={c}
          r={r}
          className="ring-value"
          stroke="url(#ring-gradient)"
          strokeWidth={stroke}
          strokeLinecap="round"
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - fraction)}
          transform={`rotate(-90 ${c} ${c})`}
        />
      </svg>
      <div className="ring-center">{children}</div>
    </div>
  );
}
