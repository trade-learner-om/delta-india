import { useState } from "react";
import { createPortal } from "react-dom";
import { ledgerMuted, money } from "./deskFormat";

const WIDTH = 320;
const HEIGHT = 120;

export default function AreaChart({ values, positive, className = "h-28", quiet = false }) {
  if (!values?.length) {
    if (quiet) return null;
    return <p className={`text-sm ${ledgerMuted}`}>No saved trades yet.</p>;
  }
  return <AreaChartSvg values={values} positive={positive} className={className} />;
}

function AreaChartSvg({ values, positive, className }) {
  const [hover, setHover] = useState(null);
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const span = max - min || 1;
  const step = values.length === 1 ? WIDTH : WIDTH / (values.length - 1);
  const points = values.map((value, index) => {
    const x = index * step;
    const y = HEIGHT - ((value - min) / span) * (HEIGHT - 8) - 4;
    return [x, y];
  });
  const line = points.map(([x, y]) => `${x},${y}`).join(" ");
  const area = `0,${HEIGHT} ${line} ${WIDTH},${HEIGHT}`;
  const stroke = positive ? "var(--ledger-profit)" : "var(--ledger-loss)";

  const onMove = (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width) return;
    const relative = ((event.clientX - rect.left) / rect.width) * WIDTH;
    let nearest = 0;
    let distance = Number.POSITIVE_INFINITY;
    points.forEach(([x], index) => {
      const delta = Math.abs(x - relative);
      if (delta < distance) {
        distance = delta;
        nearest = index;
      }
    });
    const [x, y] = points[nearest];
    setHover({
      x,
      y,
      value: values[nearest],
      clientX: event.clientX,
      clientY: event.clientY,
    });
  };

  return (
    <>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className={`w-full ${className}`}
        role="img"
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        <rect width={WIDTH} height={HEIGHT} fill="transparent" />
        <polygon points={area} fill={stroke} opacity="0.18" />
        <polyline points={line} fill="none" stroke={stroke} strokeWidth="2" />
        {hover ? (
          <g pointerEvents="none">
            <line x1={hover.x} x2={hover.x} y1="0" y2={HEIGHT} stroke={stroke} strokeWidth="1" strokeDasharray="3 3" opacity="0.7" />
            <circle cx={hover.x} cy={hover.y} r="3.5" fill={stroke} />
          </g>
        ) : null}
      </svg>
      {hover ? createPortal(
        <div
          className="pointer-events-none fixed z-50 rounded-md border border-[var(--ledger-border)] bg-[var(--ledger-surface)] px-2 py-1 text-xs text-[var(--ledger-text)] shadow-md"
          style={{
            left: Math.min(hover.clientX + 12, window.innerWidth - 96),
            top: Math.max(8, hover.clientY - 32),
          }}
        >
          {money(hover.value)}
        </div>,
        document.body,
      ) : null}
    </>
  );
}
