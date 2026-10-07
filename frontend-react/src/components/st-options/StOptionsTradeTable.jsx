import WorkspaceDataTable, {
  WorkspaceTable,
  WorkspaceTableBody,
  WorkspaceTableHead,
} from "../ui/WorkspaceDataTable";
import { profitText, lossText, textMuted } from "../../utils/workspace/workspaceClasses";
import BiasIcon from "./BiasIcon";

function exitReasonLabel(reason) {
  switch (String(reason || "")) {
    case "st_flip":
      return "Market flipped";
    case "stop_loss":
      return "Stop";
    case "take_profit":
      return "Target";
    case "manual_stop":
      return "Closed manually";
    case "end_of_data":
      return "End of period";
    case "expiry_close":
      return "Closed before expiry";
    case "expired":
      return "Settled at expiry";
    case "force_closed":
      return "Force closed";
    case "pair_parity":
      return "Premiums equal";
    case "pair_stop":
      return "Pair exit";
    case "max_loss":
      return "Max loss";
    default:
      return reason || "—";
  }
}

function fmt(n, digits = 2) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toFixed(digits);
}

function pnlClass(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "";
  return n > 0 ? profitText() : lossText();
}

function streakDisplay(len, count) {
  const l = Number(len) || 0;
  const c = Number(count) || 0;
  if (!l) return "0(0)";
  return `${l}(${c})`;
}

export function StOptionsTradeTable({
  trades,
  emptyMessage = "No trades yet.",
  badge,
  bodyClassName,
}) {
  const rows = trades || [];
  return (
    <WorkspaceDataTable
      title="Trades"
      badge={badge != null ? badge : `${rows.length}`}
      emptyMessage={rows.length ? null : emptyMessage}
      bodyClassName={bodyClassName}
    >
      {rows.length ? (
        <WorkspaceTable>
          <WorkspaceTableHead>
            <th className="px-3 py-2">Date</th>
            <th className="px-3 py-2">Side</th>
            <th className="px-3 py-2">Quantity</th>
            <th className="px-3 py-2">Bias</th>
            <th className="px-3 py-2">Bias changed</th>
            <th className="px-3 py-2">Strike</th>
            <th className="px-3 py-2">Expiry</th>
            <th className="px-3 py-2">Received</th>
            <th className="px-3 py-2">Exit</th>
            <th className="px-3 py-2">Reason</th>
            <th className="px-3 py-2 text-right">Result</th>
          </WorkspaceTableHead>
          <WorkspaceTableBody>
            {rows.map((row, index) => (
              <tr key={row.id || `${row.date}-${row.optionSymbol}-${index}`} className="hover:bg-slate-50 dark:hover:bg-zinc-950/60">
                <td className="px-3 py-2 whitespace-nowrap">{row.date || "—"}</td>
                <td className="px-3 py-2">{row.direction === "LONG" ? "Long-side" : row.direction === "SHORT" ? "Short-side" : (row.direction || "—")}</td>
                <td className="px-3 py-2 font-mono">{row.lots != null ? row.lots : "—"}</td>
                <td className="px-3 py-2">
                  <BiasIcon colour={row.stColour} className="w-6 h-6" />
                </td>
                <td className={`px-3 py-2 whitespace-nowrap ${textMuted()}`}>{row.stColourChangeTime || "—"}</td>
                <td className="px-3 py-2">{fmt(row.strike, 0)}</td>
                <td className="px-3 py-2 whitespace-nowrap">{row.expiryDate || "—"}</td>
                <td className="px-3 py-2">{fmt(row.premiumReceived)}</td>
                <td className="px-3 py-2">{fmt(row.exitPrice)}</td>
                <td className="px-3 py-2">{exitReasonLabel(row.exitReason)}</td>
                <td className={`px-3 py-2 text-right font-bold ${pnlClass(row.pnl)}`}>{fmt(row.pnl)}</td>
              </tr>
            ))}
          </WorkspaceTableBody>
        </WorkspaceTable>
      ) : null}
    </WorkspaceDataTable>
  );
}

export function StOptionsSummaryGrid({ summary }) {
  if (!summary) return null;
  const items = [
    { label: "Total trades", value: summary.totalTrades ?? 0 },
    { label: "Total PnL", value: fmt(summary.totalPnl), accent: true, raw: summary.totalPnl },
    { label: "Total wins", value: summary.winCount ?? 0 },
    { label: "Total losses", value: summary.lossCount ?? 0 },
    {
      label: "Max winning streak",
      value: streakDisplay(summary.maxWinStreakLen, summary.maxWinStreakCount),
    },
    {
      label: "Max losing streak",
      value: streakDisplay(summary.maxLossStreakLen, summary.maxLossStreakCount),
    },
    { label: "Average profit", value: fmt(summary.avgProfit), accent: true, raw: summary.avgProfit },
    { label: "Average loss", value: fmt(summary.avgLoss), accent: true, raw: summary.avgLoss },
    { label: "Long trades", value: summary.longTrades ?? 0 },
    { label: "Short trades", value: summary.shortTrades ?? 0 },
    { label: "Long PnL", value: fmt(summary.longPnl), accent: true, raw: summary.longPnl },
    { label: "Short PnL", value: fmt(summary.shortPnl), accent: true, raw: summary.shortPnl },
    {
      label: "Max profit",
      value: fmt(summary.maxProfit),
      footer: summary.maxProfitDate || null,
      accent: true,
      raw: summary.maxProfit,
    },
    {
      label: "Max loss",
      value: fmt(summary.maxLoss),
      footer: summary.maxLossDate || null,
      accent: true,
      raw: summary.maxLoss,
    },
    { label: "Max drawdown", value: fmt(summary.maxDrawdown) },
    {
      label: "Max DD duration",
      value: summary.maxDdFrom && summary.maxDdTo ? `${summary.maxDdFrom} → ${summary.maxDdTo}` : "—",
    },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
      {items.map((item) => (
        <div key={item.label} className="rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4">
          <p className={`text-[10px] font-bold uppercase tracking-widest ${textMuted()}`}>{item.label}</p>
          <p className={`text-lg font-mono font-extrabold mt-1 ${item.accent ? pnlClass(item.raw) : ""}`}>
            {item.value}
          </p>
          {item.footer ? <p className={`text-[10px] mt-2 ${textMuted()}`}>{item.footer}</p> : null}
        </div>
      ))}
    </div>
  );
}
