interface Props {
  label: string;
  value: number;
  target: number;
  color: string;
  unit?: string;
}

export default function MacroBar({ label, value, target, color, unit = "g" }: Props) {
  const pct = target > 0 ? Math.round((value / target) * 100) : 0;
  return (
    <div className="macro-bar">
      <div>
        <div className="macro-head">
          <span>{label}</span>
          <span className="muted">
            {Math.round(value)}
            {unit} / {Math.round(target)}
            {unit}
          </span>
        </div>
        <div className="macro-track" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
          <div className="macro-fill" style={{ width: `${Math.min(pct, 100)}%`, background: color }} />
        </div>
      </div>
      <span className="macro-pct" style={{ color }}>
        {pct}%
      </span>
    </div>
  );
}
