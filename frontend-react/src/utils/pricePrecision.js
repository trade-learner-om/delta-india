export function livePriceKey(symbol) {
  return String(symbol || "").toUpperCase().trim().replace(/\//g, "").replace(/-/g, "");
}

export function coerceLiveNumber(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

export function lookupLiveTick(livePrices = {}, symbol) {
  const key = livePriceKey(symbol);
  if (!key) return {};
  return livePrices?.[key] || {};
}

export function livePriceFromTick(tick) {
  if (!tick || typeof tick !== "object") return null;
  const mark = coerceLiveNumber(tick.mark_price);
  if (mark != null) return mark;
  const price = coerceLiveNumber(tick.price);
  if (price != null) return price;
  const bid = coerceLiveNumber(tick.bid);
  const ask = coerceLiveNumber(tick.ask);
  if (bid != null && ask != null) return (bid + ask) / 2;
  if (bid != null) return bid;
  if (ask != null) return ask;
  return null;
}

/** Single display value for header spot chips — matches backend display_price_from_ticker. */
export function spotDisplayPrice(tick) {
  if (!tick || typeof tick !== "object") return null;
  const mark = coerceLiveNumber(tick.mark_price);
  if (mark != null) return mark;
  const price = coerceLiveNumber(tick.price);
  if (price != null) return price;
  const bid = coerceLiveNumber(tick.bid);
  const ask = coerceLiveNumber(tick.ask);
  if (bid != null && ask != null) return (bid + ask) / 2;
  if (bid != null) return bid;
  if (ask != null) return ask;
  return null;
}

export function recomputeTickDisplayPrice(tick) {
  if (!tick || typeof tick !== "object") return tick;
  const display = spotDisplayPrice(tick);
  if (display == null) return tick;
  return { ...tick, price: display };
}

export function clampDigits(digits, fallback = 5) {
  const parsed = Number(digits);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(0, Math.min(Math.trunc(parsed), 10));
}

export function roundPriceToDigits(value, digits) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return value;
  const precision = clampDigits(digits, 5);
  return Number(numeric.toFixed(precision));
}

export function priceStepForDigits(digits) {
  const precision = clampDigits(digits, 5);
  if (precision <= 0) return "1";
  return (1 / 10 ** precision).toFixed(precision);
}

export function decimalPlaces(value) {
  if (value === null || value === undefined) return 0;
  const text = typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(10).replace(/(\.\d*?[1-9])0+$/, "$1").replace(/\.0+$/, "")
    : String(value);
  if (text.includes("e-")) {
    const [, exponent] = text.split("e-");
    return Number(exponent) || 0;
  }
  const parts = text.split(".");
  return parts[1]?.length || 0;
}

export function formatPriceWithDigits(value, digits, relatedValues = [], minimumPrecision = 0) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value !== "number" || Number.isNaN(value)) return String(value);

  const brokerDigits = digits === null || digits === undefined ? null : clampDigits(digits, 5);
  const precision = brokerDigits !== null
    ? brokerDigits
    : Math.min(Math.max(minimumPrecision, decimalPlaces(value), ...(relatedValues || []).map(decimalPlaces)), 10);
  const rounded = Number(value.toFixed(precision));
  return precision > 0 ? rounded.toFixed(precision) : String(Math.round(rounded));
}

export function resolveSymbolPriceDigits(symbol, livePrices = {}, symbolPriceDigits = {}) {
  const key = livePriceKey(symbol);
  if (!key) return null;
  const tickDigits = livePrices?.[key]?.price_digits;
  if (tickDigits !== null && tickDigits !== undefined) return clampDigits(tickDigits, 5);
  const cached = symbolPriceDigits?.[key] ?? symbolPriceDigits?.[symbol];
  if (cached !== null && cached !== undefined) return clampDigits(cached, 5);
  return null;
}

export function resolvePriceDigitsForSymbol(
  symbol,
  { livePrices = {}, symbolPriceDigits = {}, liveTick = null, fallback = 2 } = {},
) {
  if (liveTick?.price_digits !== null && liveTick?.price_digits !== undefined) {
    return clampDigits(liveTick.price_digits, fallback);
  }
  const resolved = resolveSymbolPriceDigits(symbol, livePrices, symbolPriceDigits);
  return resolved !== null ? resolved : fallback;
}
