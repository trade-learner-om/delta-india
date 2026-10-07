import WorkspaceCard from "../ui/WorkspaceCard";
import { textMuted, textHeading, profitText, lossText } from "../../utils/workspace/workspaceClasses";
import { formatDateTime } from "../../utils/optionsDisplayUtils";

function tradeLabel(trade) {
  if (trade.optionSymbol) return trade.optionSymbol;
  const side =
    trade.direction === "LONG" ? "Long" : trade.direction === "SHORT" ? "Short" : null;
  if (trade.underlying && side) return `${trade.underlying} ${side}`;
  return trade.underlying || "Trade";
}

function pnlClass(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "text-slate-800 dark:text-zinc-100";
  return n > 0 ? profitText() : lossText();
}

export default function DashboardRecentTrades({ trades = [], limit = 10 }) {
  const rows = [...(trades || [])]
    .filter((t) => t && (t.exitTime != null || t.status === "closed" || t.pnl != null))
    .sort((a, b) => {
      const ta = Number(a.exitTime) || 0;
      const tb = Number(b.exitTime) || 0;
      return tb - ta;
    })
    .slice(0, limit);

  return (
    <WorkspaceCard className="flex flex-col min-h-[220px]">
      <div className="mb-3">
        <h3 className={`text-sm font-bold uppercase tracking-wider ${textHeading()}`}>Recent Trades</h3>
        <p className={`text-xs ${textMuted()}`}>Closed ST Options — square-off and PnL</p>
      </div>
      {!rows.length ? (
        <div className={`flex flex-1 items-center justify-center text-xs ${textMuted()}`}>
          No closed trades yet.
        </div>
      ) : (
        <ul className="space-y-2 overflow-auto max-h-52 pr-1">
          {rows.map((trade) => {
            const pnl = Number(trade.pnl);
            return (
              <li
                key={trade.id || `${trade.optionSymbol}-${trade.exitTime}`}
                className="flex items-start justify-between gap-3 text-xs border-b border-slate-100 dark:border-zinc-800 pb-2 last:border-0 last:pb-0"
              >
                <div className="min-w-0">
                  <p className={`font-semibold truncate ${textHeading()}`}>{tradeLabel(trade)}</p>
                  <p className={`font-mono text-[10px] mt-0.5 ${textMuted()}`}>
                    Qty {trade.lots != null ? Number(trade.lots) : "—"} · {formatDateTime(trade.exitTime)}
                  </p>
                </div>
                <p className={`font-mono font-bold tabular-nums shrink-0 ${pnlClass(pnl)}`}>
                  {Number.isFinite(pnl) ? pnl.toFixed(2) : "—"}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </WorkspaceCard>
  );
}
