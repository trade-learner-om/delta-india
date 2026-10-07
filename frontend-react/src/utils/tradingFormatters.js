const USD_MONEY_OPTIONS = {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
};

export function formatUsdMoney(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString("en-IN", USD_MONEY_OPTIONS);
}

export function formatPremium(value) {
  return formatUsdMoney(value);
}

export function formatPnl(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const numeric = Number(value);
  const prefix = numeric > 0 ? "+" : "";
  return `${prefix}${numeric.toLocaleString("en-IN", USD_MONEY_OPTIONS)}`;
}

export function formatStrike(value) {
  if (value == null) return "—";
  return Number(value).toLocaleString("en-IN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

export function formatTimestamp(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatEpochSeconds(value) {
  if (value == null) return "—";
  return formatTimestamp(Number(value) * 1000);
}

export function formatPercent(value, digits = 1) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

export function isoDaysAgo(days) {
  const date = new Date(Date.now() - days * 24 * 3600 * 1000);
  return date.toISOString().slice(0, 10);
}

export function isoToday() {
  return new Date().toISOString().slice(0, 10);
}
