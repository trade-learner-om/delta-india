export const MARGIN_THRESHOLD = 1000;
export const LOW_MARGIN_CAP = 10;
export const HIGH_MARGIN_RATE = 0.01;

export function maxRiskAmount(availableMargin) {
  const margin = Number(availableMargin);
  if (!Number.isFinite(margin) || margin <= 0) return 0;
  if (margin < MARGIN_THRESHOLD) return LOW_MARGIN_CAP;
  return margin * HIGH_MARGIN_RATE;
}

export function maxRiskCapLabel() {
  return "max $10 below $1,000 margin, else 1% of margin";
}
