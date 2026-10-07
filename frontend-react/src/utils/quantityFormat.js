export function inferBaseCurrency(symbol, fallback = "BTC") {
  const normalized = String(symbol || "").trim().toUpperCase();
  if (!normalized) return fallback;
  if (normalized.startsWith("BTC")) return "BTC";
  if (normalized.startsWith("ETH")) return "ETH";
  if (normalized.startsWith("SOL")) return "SOL";
  const stripped = normalized.replace(/(USD|INR|USDT|PERP).*$/i, "");
  return stripped || fallback;
}

function formatBaseUnits(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "0";
  if (numeric >= 1) {
    return numeric.toFixed(4).replace(/\.?0+$/, "");
  }
  return numeric.toFixed(6).replace(/\.?0+$/, "");
}

function formatLots(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "0";
  if (Math.abs(numeric - Math.round(numeric)) < 1e-9) {
    return String(Math.round(numeric));
  }
  return numeric.toFixed(2).replace(/\.?0+$/, "");
}

export function formatQuantityLabel(source, symbol = "") {
  if (!source) return "—";
  if (typeof source === "string" || typeof source === "number") {
    return String(source);
  }
  if (source.quantity_label || source.quantityLabel) {
    return source.quantity_label || source.quantityLabel;
  }

  const lots = Number(
    source.lots ?? source.quantity ?? source.size ?? source.unfilled_size,
  );
  const contractValue = Number(source.contract_value ?? source.contractValue ?? 1);
  const baseCurrency = (
    source.base_currency
    ?? source.baseCurrency
    ?? source.contract_unit_currency
    ?? inferBaseCurrency(symbol || source.symbol)
  ).toUpperCase();

  if (!Number.isFinite(lots)) return "—";
  const baseUnits = Number.isFinite(Number(source.base_units ?? source.baseUnits))
    ? Number(source.base_units ?? source.baseUnits)
    : lots * contractValue;

  return `${formatBaseUnits(baseUnits)} ${baseCurrency} / ${formatLots(lots)} lots`;
}

export function formatMoney(value, currency = "USD") {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return `${numeric.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} ${currency}`;
}

export function readTradeEconomics(preview) {
  if (!preview) return null;
  return {
    requiredMargin: preview.required_margin ?? preview.requiredMargin,
    estimatedCommission: preview.estimated_commission ?? preview.estimatedCommission,
    marginCurrency: preview.margin_currency ?? preview.marginCurrency ?? preview.settling_asset ?? "USD",
    feeCurrency: preview.fee_currency ?? preview.feeCurrency ?? preview.settling_asset ?? "USD",
    commissionRate: preview.commission_rate ?? preview.commissionRate,
  };
}
