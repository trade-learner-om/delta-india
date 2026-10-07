import WorkspaceDataTable, { WorkspaceTable, WorkspaceTableBody, WorkspaceTableHead } from "../ui/WorkspaceDataTable";
import { formatOrderTime } from "./positionsUtils";
import { tableCell, tableCellStrong, textMuted, profitText, lossText } from "../../utils/workspace/workspaceClasses";

export default function PositionsPastOrdersTable({ orders, loading }) {
  return (
    <WorkspaceDataTable
      title="Past Orders"
      emptyMessage={loading ? "Loading order history…" : "No past orders found."}
    >
      {orders?.length ? (
        <WorkspaceTable>
          <WorkspaceTableHead>
            <th className="p-4">Time</th>
            <th className="p-4">Instrument</th>
            <th className="p-4">Side</th>
            <th className="p-4">Type</th>
            <th className="p-4 text-right">Price</th>
            <th className="p-4 text-right">Size</th>
            <th className="p-4">Status</th>
          </WorkspaceTableHead>
          <WorkspaceTableBody>
            {orders.map((order) => (
              <tr key={order.id} className={`hover:bg-slate-100 dark:hover:bg-zinc-950/20 font-mono ${tableCell()}`}>
                <td className={`p-4 ${textMuted()}`}>{formatOrderTime(order.createdAt)}</td>
                <td className={`p-4 font-bold ${tableCellStrong()}`}>{order.symbol || order.coin}</td>
                <td className={`p-4 font-bold ${order.side === "BUY" ? profitText() : lossText()}`}>{order.side}</td>
                <td className="p-4">{order.orderType}</td>
                <td className="p-4 text-right">{order.price ?? "—"}</td>
                <td className="p-4 text-right">{order.size ?? "—"}</td>
                <td className="p-4">{order.status}</td>
              </tr>
            ))}
          </WorkspaceTableBody>
        </WorkspaceTable>
      ) : null}
    </WorkspaceDataTable>
  );
}
