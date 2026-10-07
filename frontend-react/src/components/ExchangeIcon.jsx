const ICONS = {
  delta: { label: "Delta", bg: "bg-orange-100", text: "text-orange-700", glyph: "D" },
};

export default function ExchangeIcon({ exchange = "delta", size = 22, showLabel = false, className = "" }) {
  const key = String(exchange || "delta").toLowerCase();
  const icon = ICONS[key] || ICONS.delta;
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <span
        className={`inline-flex items-center justify-center rounded-full font-black ${icon.bg} ${icon.text}`}
        style={{ width: size, height: size, fontSize: Math.max(10, Math.round(size * 0.45)) }}
      >
        {icon.glyph}
      </span>
      {showLabel ? <span className="text-sm font-semibold text-slate-700">{icon.label}</span> : null}
    </span>
  );
}
