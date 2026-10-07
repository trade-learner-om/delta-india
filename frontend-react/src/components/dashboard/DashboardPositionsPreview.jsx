import WorkspaceCard from "../ui/WorkspaceCard";
import { formatUsdWithSymbol, pnlColorClass } from "../../utils/workspace/workspaceFormatters";
import { textMuted, textHeading, textBody } from "../../utils/workspace/workspaceClasses";

export default function DashboardPositionsPreview({ positions, accounts, onNavigate }) {
  return (
    <WorkspaceCard className="lg:col-span-2 space-y-4">
      <div className="flex justify-between items-center">
        <h3 className={`text-sm font-bold uppercase tracking-wider ${textHeading()}`}>Active Option Desks</h3>
        <button
          type="button"
          onClick={() => onNavigate("positions")}
          className="text-xs text-lime-600 dark:text-lime-400 hover:underline transition"
        >
          Unified ledger →
        </button>
      </div>
      <div className="overflow-x-auto font-sans text-xs">
        <table className="w-full text-left">
          <thead>
            <tr className={`border-b border-slate-200 dark:border-zinc-800 uppercase tracking-widest text-[9px] font-extrabold ${textMuted()}`}>
              <th className="pb-3">Desk ID</th>
              <th className="pb-3">Contract Symbol</th>
              <th className="pb-3">Endpoint Target</th>
              <th className="pb-3 text-right">Size Lots</th>
              <th className="pb-3 text-right">PnL (USD)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-zinc-850/80 font-mono text-slate-700 dark:text-zinc-300">
            {(positions || []).slice(0, 8).map((pos) => {
              const account = accounts.find((item) => item.id === pos.accountId);
              const pnl = Number(pos.unrealizedPnlUsd) || 0;
              return (
                <tr key={pos.id} className="hover:bg-slate-100 dark:hover:bg-zinc-950/40">
                  <td className="py-3">
                    <span className={`px-2 py-0.5 bg-slate-200 dark:bg-zinc-800 rounded-md text-[10px] font-sans ${textBody()}`}>
                      Options spread
                    </span>
                  </td>
                  <td className={`py-3 font-bold ${textHeading()}`}>{pos.symbol}</td>
                  <td className={`py-3 ${textMuted()}`}>{account?.accountName || account?.account_name || "—"}</td>
                  <td className={`py-3 text-right font-bold ${Number(pos.signedSize) > 0 ? "text-lime-600 dark:text-lime-400" : "text-red-500 dark:text-red-400"}`}>
                    {pos.signedSize ?? pos.size ?? "—"}
                  </td>
                  <td className={`py-3 text-right font-bold ${pnlColorClass(pnl)}`}>
                    {formatUsdWithSymbol(pnl, { signed: true })}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!positions?.length ? (
          <p className={`py-8 text-center text-xs ${textMuted()}`}>No open positions.</p>
        ) : null}
      </div>
    </WorkspaceCard>
  );
}
