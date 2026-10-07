import WorkspaceDataTable, { WorkspaceTable, WorkspaceTableBody, WorkspaceTableHead } from "../ui/WorkspaceDataTable";
import { tableCell, tableCellStrong, profitText, lossText } from "../../utils/workspace/workspaceClasses";

export default function PositionsOpenOrdersTable({ orders, title = "Delta" }) {
  return (
    <WorkspaceDataTable
      title={`Open Orders — ${title}`}
      emptyMessage={`No open orders on ${title}.`}
    >
      {orders?.length ? (
        <WorkspaceTable>
          <WorkspaceTableHead>
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
                <td className={`p-4 font-bold ${tableCellStrong()}`}>{order.symbol || order.coin}</td>
                <td className={`p-4 font-bold ${order.side === "BUY" ? profitText() : lossText()}`}>{order.side}</td>
                <td className="p-4">{order.orderType}</td>
                <td className="p-4 text-right">{order.price ?? "—"}</td>
                <td className="p-4 text-right">{order.size ?? order.unfilledSize ?? "—"}</td>
                <td className="p-4">{order.status}</td>
              </tr>
            ))}
          </WorkspaceTableBody>
        </WorkspaceTable>
      ) : null}
    </WorkspaceDataTable>
  );
}
