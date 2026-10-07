export const DEFAULT_PREVIEW_IV_PCT = 55;

export function normalizeOptionSymbol(symbol) {
  return String(symbol || "").toUpperCase().trim();
}

export function parseOptionSymbol(symbol) {
  const normalized = normalizeOptionSymbol(symbol);
  const match = normalized.match(/^([CP])-([A-Z]+)-(\d+(?:\.\d+)?)-(\d{6})$/);
  if (!match) return null;
  const [, cp, underlying, strikeRaw, expiryRaw] = match;
  const day = Number(expiryRaw.slice(0, 2));
  const month = Number(expiryRaw.slice(2, 4));
  const year = 2000 + Number(expiryRaw.slice(4, 6));
  const expiry = new Date(Date.UTC(year, month - 1, day, 11, 30, 0));
  return {
    type: cp === "C" ? "call" : "put",
    underlying,
    strike: Number(strikeRaw),
    expiry,
  };
}

function erf(x) {
  const sign = x < 0 ? -1 : 1;
  const abs = Math.abs(x);
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;
  const t = 1 / (1 + p * abs);
  const y = 1 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-abs * abs);
  return sign * y;
}

function normCdf(x) {
  return 0.5 * (1 + erf(x / Math.SQRT2));
}

export function blackScholesPrice(spot, strike, tteYears, vol, type) {
  const s = Number(spot);
  const k = Number(strike);
  const t = Math.max(Number(tteYears) || 0, 1 / 365);
  const sigma = Math.max(Number(vol) || 0, 1e-4);
  if (!Number.isFinite(s) || !Number.isFinite(k) || s <= 0 || k <= 0) return 0;
  const sqrtT = Math.sqrt(t);
  const d1 = (Math.log(s / k) + 0.5 * sigma * sigma * t) / (sigma * sqrtT);
  const d2 = d1 - sigma * sqrtT;
  if (type === "put") {
    return k * normCdf(-d2) - s * normCdf(-d1);
  }
  return s * normCdf(d1) - k * normCdf(d2);
}

export function impliedVolatility(target, spot, strike, tteYears, type) {
  const premium = Number(target);
  if (!Number.isFinite(premium) || premium <= 0) return DEFAULT_PREVIEW_IV_PCT / 100;
  let low = 0.01;
  let high = 5.0;
  for (let i = 0; i < 64; i += 1) {
    const mid = (low + high) / 2;
    const estimate = blackScholesPrice(spot, strike, tteYears, mid, type);
    if (estimate > premium) {
      high = mid;
    } else {
      low = mid;
    }
  }
  return (low + high) / 2;
}

export function timeToExpiryYears(expiryDate, now = Date.now()) {
  return Math.max((expiryDate.getTime() - now) / (365 * 24 * 60 * 60 * 1000), 1 / 365);
}

export function contractValueFor(row) {
  const parsed = parseOptionSymbol(row.symbol);
  if (Number.isFinite(Number(row.contractValue))) return Number(row.contractValue);
  if (parsed?.underlying === "ETH") return 0.01;
  return parsed ? 0.001 : 1;
}

export function signedBaseUnitsFor(row) {
  const direct = Number(row.signedBaseUnits);
  if (Number.isFinite(direct) && direct !== 0) return direct;
  const signedSize = Number(row.signedSize);
  const cv = contractValueFor(row);
  if (Number.isFinite(signedSize) && Number.isFinite(cv)) return signedSize * cv;
  return 0;
}

export function underlyingFromRow(row) {
  const parsed = parseOptionSymbol(row.symbol);
  return parsed?.underlying || String(row.coin || "BTC").toUpperCase();
}

export function resolveLiveSpot(underlying, livePrices = {}) {
  const liveTick = livePrices?.[`${underlying}USD`] || livePrices?.[underlying] || null;
  const liveSpot = Number(liveTick?.mark_price ?? liveTick?.price ?? liveTick?.bid ?? liveTick?.ask);
  return Number.isFinite(liveSpot) && liveSpot > 0 ? liveSpot : null;
}
