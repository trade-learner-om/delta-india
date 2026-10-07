import { formatMoney, readTradeEconomics } from "../utils/quantityFormat";

export default function TradeEconomics({ preview, className = "" }) {
  const economics = readTradeEconomics(preview);
  if (!economics) return null;
  const rate = Number(economics.commissionRate);
  const rateLabel = Number.isFinite(rate) && rate > 0 ? ` (${(rate * 100).toFixed(3)}%)` : "";

  return (
    <div className={`grid gap-2 text-sm sm:grid-cols-2 ${className}`}>
      <div>
        <span className="block text-xs uppercase tracking-wide text-slate-500">Required margin</span>
        <span className="font-semibold text-slate-900">
          {formatMoney(economics.requiredMargin, economics.marginCurrency)}
        </span>
      </div>
      <div>
        <span className="block text-xs uppercase tracking-wide text-slate-500">Est. charges{rateLabel}</span>
        <span className="font-semibold text-slate-900">
          {formatMoney(economics.estimatedCommission, economics.feeCurrency)}
        </span>
      </div>
    </div>
  );
}
