import WorkspaceDataTable, {
  WorkspaceTable,
  WorkspaceTableBody,
  WorkspaceTableHead,
} from "../ui/WorkspaceDataTable";
import { textMuted } from "../../utils/workspace/workspaceClasses";
import { statusTone } from "./executionUtils";

function toneClass(tone) {
  if (tone === "lime") return "bg-lime-400/20 text-lime-800 dark:text-lime-300";
  if (tone === "amber") return "bg-amber-400/20 text-amber-900 dark:text-amber-300";
  if (tone === "blue") return "bg-sky-400/20 text-sky-900 dark:text-sky-300";
  if (tone === "red") return "bg-red-400/20 text-red-800 dark:text-red-300";
  return "bg-slate-200 dark:bg-zinc-800 text-slate-700 dark:text-zinc-300";
}

export default function ExecutionMonitorTable({ monitors = [], onCancel, pending }) {
  const rows = monitors || [];

  if (!rows.length) {
    return (
      <WorkspaceDataTable title="Active Monitors" emptyMessage="No execution monitors yet." />
    );
  }

  return (
    <WorkspaceDataTable title="Active Monitors" badge={`${rows.length}`}>
      <WorkspaceTable>
        <WorkspaceTableHead>
          <th className="px-3 py-2">Status</th>
          <th className="px-3 py-2">Option</th>
          <th className="px-3 py-2">Lots</th>
          <th className="px-3 py-2">Entry</th>
          <th className="px-3 py-2">Spot SL</th>
          <th className="px-3 py-2">Last spot</th>
          <th className="px-3 py-2" />
        </WorkspaceTableHead>
        <WorkspaceTableBody>
          {rows.map((row) => {
            const cancellable = row.status === "Pending Trigger" || row.status === "Order Placed";
            return (
              <tr key={row.id} className="hover:bg-slate-50 dark:hover:bg-zinc-900/50">
                <td className="px-3 py-2">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${toneClass(statusTone(row.status))}`}>
                    {row.status}
                    {row.safeMode ? " · SAFE" : ""}
                  </span>
                </td>
                <td className="px-3 py-2">{row.optionSymbol}</td>
                <td className="px-3 py-2">{row.quantityLots}</td>
                <td className="px-3 py-2">
                  {row.entrySpotLevel} ({row.entrySpotOperator})
                </td>
                <td className="px-3 py-2">
                  {row.spotStopLevel} ({row.spotStopOperator})
                </td>
                <td className="px-3 py-2">{row.lastSpotPrice ?? "—"}</td>
                <td className="px-3 py-2">
                  {cancellable ? (
                    <button
                      type="button"
                      disabled={pending}
                      onClick={() => onCancel?.(row.id)}
                      className="text-[10px] font-bold uppercase text-red-600 dark:text-red-400 hover:underline disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  ) : (
                    <span className={textMuted()}>—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </WorkspaceTableBody>
      </WorkspaceTable>
    </WorkspaceDataTable>
  );
}
