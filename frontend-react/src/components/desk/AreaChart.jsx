import { ledgerMuted } from "./deskFormat";

export default function AreaChart({ values, positive, className = "h-28", quiet = false }) {
  const width = 320;
  const height = 120;
  if (!values?.length) {
    if (quiet) return null;
    return <p className={`text-sm ${ledgerMuted}`}>No saved trades yet.</p>;
  }
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const span = max - min || 1;
  const step = values.length === 1 ? width : width / (values.length - 1);
  const points = values.map((value, index) => {
    const x = index * step;
    const y = height - ((value - min) / span) * (height - 8) - 4;
    return [x, y];
  });
  const line = points.map(([x, y]) => `${x},${y}`).join(" ");
  const area = `0,${height} ${line} ${width},${height}`;
  const stroke = positive ? "var(--ledger-profit)" : "var(--ledger-loss)";
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={`w-full ${className}`} role="img">
      <polygon points={area} fill={stroke} opacity="0.18" />
      <polyline points={line} fill="none" stroke={stroke} strokeWidth="2" />
    </svg>
  );
}
