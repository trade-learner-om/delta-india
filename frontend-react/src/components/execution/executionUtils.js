import { lookupLiveTick, livePriceFromTick } from "../../utils/pricePrecision";

export const LOTS_PER_UNIT = { BTC: 1000, ETH: 100 };

export function lotsHint(underlying) {
  const coin = String(underlying || "").toUpperCase();
  const lots = LOTS_PER_UNIT[coin];
  if (!lots) return "";
  return `1 ${coin} = ${lots} lots`;
}

export function spotSymbolForUnderlying(underlying) {
  const coin = String(underlying || "").toUpperCase();
  if (coin === "BTC" || coin === "ETH") return `${coin}USD`;
  return "";
}

export function readOptionLivePrice(livePrices, symbol) {
  if (!symbol) return null;
  const tick = lookupLiveTick(livePrices, symbol);
  return livePriceFromTick(tick);
}

export function formatOptionPrice(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  const digits = numeric >= 100 ? 2 : numeric >= 1 ? 4 : 6;
  return numeric.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: digits,
  });
}

export function readSpotPrice(livePrices, underlying) {
  const symbol = spotSymbolForUnderlying(underlying);
  if (!symbol) return null;
  const tick = lookupLiveTick(livePrices, symbol);
  return livePriceFromTick(tick);
}

export function willExecuteImmediately(option, spotPrice) {
  if (!option || spotPrice == null) return false;
  const strike = Number(option.strikePrice);
  const spot = Number(spotPrice);
  if (!Number.isFinite(strike) || !Number.isFinite(spot)) return false;
  const type = String(option.optionType || "").toUpperCase();
  if (type === "CE") return spot >= strike;
  if (type === "PE") return spot <= strike;
  return false;
}

export function activeMonitorCount(monitors = []) {
  const active = new Set(["Pending Trigger", "Order Placed", "Order Filled", "Closing"]);
  return monitors.filter((row) => active.has(row.status)).length;
}

export function statusTone(status) {
  switch (status) {
    case "Pending Trigger":
      return "amber";
    case "Order Placed":
      return "blue";
    case "Order Filled":
      return "lime";
    case "Squared Off":
      return "neutral";
    case "Cancelled":
      return "neutral";
    case "Failed":
      return "red";
    default:
      return "neutral";
  }
}
