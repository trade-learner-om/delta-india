const COIN_ICONS = {
  BTC: "/btc.svg",
  ETH: "/eth.svg",
  SOL: "/sol.svg",
};

function resolveKey(coin) {
  const raw = String(coin || "").toUpperCase().trim();
  if (!raw) return null;
  if (COIN_ICONS[raw]) return raw;
  return Object.keys(COIN_ICONS).find((key) => raw.startsWith(key)) || null;
}

export function hasCoinIcon(coin) {
  return resolveKey(coin) != null;
}

export default function CoinIcon({ coin, size = 24, className = "" }) {
  const key = resolveKey(coin);
  const label = String(coin || "").toUpperCase();

  if (key) {
    return (
      <img
        src={COIN_ICONS[key]}
        alt={key}
        title={label}
        width={size}
        height={size}
        style={{ width: size, height: size }}
        className={`inline-block shrink-0 object-contain ${className}`}
      />
    );
  }

  return (
    <span
      title={label}
      style={{ width: size, height: size, fontSize: Math.max(9, Math.round(size * 0.32)) }}
      className={`inline-flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-slate-700 to-slate-900 font-bold text-white ${className}`}
    >
      {label.slice(0, 3) || "?"}
    </span>
  );
}
