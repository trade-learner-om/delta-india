import WorkspaceKpiCard from "../ui/WorkspaceKpiCard";
import { formatUsdWithSymbol } from "../../utils/workspace/workspaceFormatters";

export default function PositionsKpiRow({ totals }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <WorkspaceKpiCard
        label="Unified Net PnL"
        value={formatUsdWithSymbol(totals.totPnl, { signed: true })}
        accent
        footer={<span>{totals.count} contracts</span>}
      />
      <WorkspaceKpiCard
        label="BTC Open Legs"
        value={`${totals.btcContracts} Positions Active`}
        footer={<span className="text-xs bg-lime-500/10 text-lime-600 dark:text-lime-400 px-2 py-1 rounded-md font-mono font-bold">BTC Desk</span>}
      />
      <WorkspaceKpiCard
        label="ETH Open Legs"
        value={`${totals.ethContracts} Positions Active`}
        footer={<span className="text-xs bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 px-2 py-1 rounded-md font-mono font-bold">ETH Desk</span>}
      />
    </div>
  );
}
