import {
  blackScholesPrice,
  impliedVolatility,
  parseOptionSymbol,
  resolveLiveSpot,
  signedBaseUnitsFor,
  underlyingFromRow,
} from "./optionPricing.js";

function priceCurveForRow(row, spot, tteNowYears) {
  const parsed = parseOptionSymbol(row.symbol);
  if (!parsed) {
    const signedBase = signedBaseUnitsFor(row);
    const entry = Number(row.entryPrice) || 0;
    return (candidateSpot) => (candidateSpot - entry) * signedBase;
  }

  const entry = Number(row.entryPrice) || 0;
  const mark = Number(row.markPrice);
  const signedBase = signedBaseUnitsFor(row);
  const tte = Math.max((parsed.expiry.getTime() - Date.now()) / (365 * 24 * 60 * 60 * 1000), tteNowYears);
  const referenceSpot = Number(spot) || Number(row.markPrice) || parsed.strike;
  const referencePremium = Number.isFinite(mark) && mark > 0 ? mark : entry;
  const iv = impliedVolatility(referencePremium, referenceSpot, parsed.strike, tte, parsed.type);

  return (candidateSpot) => {
    const theoretical = blackScholesPrice(candidateSpot, parsed.strike, tte, iv, parsed.type);
    return (theoretical - entry) * signedBase;
  };
}

export function buildSelectedPositionsPayoff(rows, livePrices = {}) {
  const selected = (rows || []).filter(Boolean);
  if (!selected.length) return null;

  const underlying = underlyingFromRow(selected[0]);
  if (!selected.every((row) => underlyingFromRow(row) === underlying)) return null;

  const liveSpot = resolveLiveSpot(underlying, livePrices);
  const entrySpots = selected
    .map((row) => Number(row.entryPrice))
    .filter((value) => Number.isFinite(value) && value > 0);
  const strikes = selected
    .map((row) => parseOptionSymbol(row.symbol)?.strike)
    .filter((value) => Number.isFinite(value));
  const anchorSpot = liveSpot
    ?? (strikes.length ? strikes.reduce((sum, value) => sum + value, 0) / strikes.length : (entrySpots[0] || 1));
  const maxStrike = strikes.length ? Math.max(...strikes) : anchorSpot;
  const minStrike = strikes.length ? Math.min(...strikes) : anchorSpot;
  const span = Math.max(anchorSpot * 0.45, (maxStrike - minStrike) * 2.4, 1000);
  const minSpot = Math.max(1, Math.min(minStrike, anchorSpot) - span);
  const maxSpot = Math.max(maxStrike, anchorSpot) + span;
  const curves = selected.map((row) => priceCurveForRow(row, anchorSpot, 7 / 365));
  const points = Array.from({ length: 121 }, (_, index) => {
    const spot = minSpot + ((maxSpot - minSpot) * index) / 120;
    const pnl = curves.reduce((sum, curve) => sum + curve(spot), 0);
    return {
      spot: Number(spot.toFixed(2)),
      pnl: Number(pnl.toFixed(4)),
    };
  });

  const breakevens = [];
  for (let i = 1; i < points.length; i += 1) {
    const prev = points[i - 1];
    const next = points[i];
    if (prev.pnl === 0) breakevens.push(prev.spot);
    if ((prev.pnl < 0 && next.pnl > 0) || (prev.pnl > 0 && next.pnl < 0)) {
      const ratio = Math.abs(prev.pnl) / (Math.abs(prev.pnl) + Math.abs(next.pnl));
      breakevens.push(Number((prev.spot + ratio * (next.spot - prev.spot)).toFixed(2)));
    }
  }

  const pnls = points.map((point) => point.pnl);
  const peakPnl = Math.max(...pnls);
  const worstPnl = Math.min(...pnls);
  const peakSpot = points[pnls.indexOf(peakPnl)]?.spot ?? anchorSpot;

  return {
    title: selected.length === 1 ? "Selected position payoff" : `Selected positions payoff (${selected.length})`,
    points,
    spot: anchorSpot,
    strike: strikes.length ? strikes.reduce((sum, value) => sum + value, 0) / strikes.length : anchorSpot,
    breakevens,
    peakSpot,
    peakPnl,
    maxProfitAtSellExpiry: peakPnl,
    worstPnlAtSellExpiry: worstPnl,
    strategyMaxLoss: worstPnl < 0 ? Number(worstPnl.toFixed(4)) : 0,
    targetPnl: null,
    stopPnl: null,
  };
}
