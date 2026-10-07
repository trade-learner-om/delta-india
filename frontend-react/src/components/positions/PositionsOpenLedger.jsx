import WorkspaceDataTable, { WorkspaceTable, WorkspaceTableBody, WorkspaceTableHead } from "../ui/WorkspaceDataTable";
import { formatPrice, formatUsd } from "./positionsUtils";
import { pnlColorClass } from "../../utils/workspace/workspaceFormatters";
import { tableCell, tableCellStrong } from "../../utils/workspace/workspaceClasses";

function SelectionCell({ checked, onChange }) {
  return (
    <label className="inline-flex cursor-pointer items-center justify-center">
      <input type="checkbox" checked={checked} onChange={onChange} className="peer sr-only" />
      <span className="inline-flex h-4 w-4 items-center justify-center rounded border border-slate-300 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-lime-600 dark:text-lime-400 transition peer-checked:border-lime-500 dark:peer-checked:border-lime-400 peer-checked:bg-lime-500/10 dark:peer-checked:bg-lime-400/20">
        {checked ? (
          <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.2">
            <path d="M3.5 8.2 6.5 11l6-6.4" />
          </svg>
        ) : null}
      </span>
    </label>
  );
}

export default function PositionsOpenLedger({
  rows,
  accounts,
  loading,
  selectedIds = [],
  onToggleRow,
  onToggleAll,
}) {
  const allSelected = rows.length > 0 && rows.every((row) => selectedIds.includes(row.id));
  const showSelection = Boolean(onToggleRow);

  return (
    <WorkspaceDataTable
      title="Live Option Ledger"
      badge="Live syncing"
      emptyMessage={loading ? "Loading positions…" : "No active open option positions found."}
    >
      {rows.length ? (
        <WorkspaceTable>
          <WorkspaceTableHead>
            {showSelection ? (
              <th className="p-4 w-10">
                <SelectionCell checked={allSelected} onChange={() => onToggleAll?.()} />
              </th>
            ) : null}
            <th className="p-4">Account Profile</th>
            <th className="p-4">Strike Contract</th>
            <th className="p-4">Direction</th>
            <th className="p-4 text-right">Position Size</th>
            <th className="p-4 text-right">Avg Entry</th>
            <th className="p-4 text-right">Mark</th>
            <th className="p-4 text-right">Running PnL</th>
          </WorkspaceTableHead>
          <WorkspaceTableBody>
            {rows.map((row) => {
              const account = accounts.find((item) => item.id === row.accountId);
              const pnl = Number(row.unrealizedPnlUsd) || 0;
              const side = row.side === "LONG" || row.side === "BUY" ? "BUY" : "SELL";
              const checked = selectedIds.includes(row.id);
              return (
                <tr key={row.id} className={`hover:bg-slate-100 dark:hover:bg-zinc-950/20 transition-colors ${checked ? "bg-lime-500/5 dark:bg-lime-400/5" : ""}`}>
                  {showSelection ? (
                    <td className="p-4">
                      <SelectionCell checked={checked} onChange={() => onToggleRow?.(row.id)} />
                    </td>
                  ) : null}
                  <td className="p-4">
                    <span className={`font-sans font-semibold block ${tableCellStrong()}`}>{account?.accountName || account?.account_name || "—"}</span>
                  </td>
                  <td className={`p-4 font-bold ${tableCellStrong()}`}>{row.symbol}</td>
                  <td className="p-4">
                    <span className={`px-2 py-0.5 rounded-md text-[10px] font-bold font-sans ${
                      side === "BUY" ? "bg-lime-500/10 text-lime-600 dark:text-lime-400 border border-lime-500/20 dark:border-lime-400/20" : "bg-red-500/10 text-red-600 dark:text-red-400 border border-red-500/20"
                    }`}>
                      {side}
                    </span>
                  </td>
                  <td className="p-4 text-right">{row.signedBaseUnits ?? row.size ?? "—"}</td>
                  <td className="p-4 text-right">{formatPrice(row.entryPrice)}</td>
                  <td className="p-4 text-right">{formatPrice(row.markPrice)}</td>
                  <td className={`p-4 text-right font-bold ${pnlColorClass(pnl)}`}>{formatUsd(pnl)}</td>
                </tr>
              );
            })}
          </WorkspaceTableBody>
        </WorkspaceTable>
      ) : null}
    </WorkspaceDataTable>
  );
}
