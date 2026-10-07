import WorkspaceKpiCard from "../ui/WorkspaceKpiCard";
import { formatUsdWithSymbol } from "../../utils/workspace/workspaceFormatters";
import { formatMargin, readAccountCurrency } from "../../utils/accountMargin";
import { accentText, textMuted, textBody } from "../../utils/workspace/workspaceClasses";

export default function DashboardKpiGrid({ metrics, accountCount }) {
  const marginLabel = metrics.availableMargin != null
    ? formatMargin(metrics.availableMargin, readAccountCurrency(metrics.activeAccount))
    : "—";

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <WorkspaceKpiCard
        label="Aggregated Net Equity"
        value={formatUsdWithSymbol(metrics.totalEquity)}
        footer={
          <div className="flex justify-between items-center">
            <span>Aggregated ({accountCount} accounts)</span>
            <span className={`font-mono font-semibold ${accentText()}`}>Decrypted Node Active</span>
          </div>
        }
      />
      <WorkspaceKpiCard
        label="Active Account Available Margin"
        value={marginLabel}
        valueClassName="text-lime-600 dark:text-lime-400 animate-pulse"
        footer={
          <span className={textMuted()}>
            Context: <strong className={`${textBody()} font-bold`}>{metrics.activeAccount?.accountName || metrics.activeAccount?.account_name || "—"}</strong>
          </span>
        }
      />
      <WorkspaceKpiCard
        label="Open Options Legs"
        value={`${metrics.openCount} active positions`}
        footer={
          <span>
            Exposure: <strong className={`${textBody()} font-bold`}>{formatUsdWithSymbol(metrics.totalNotional)}</strong>
          </span>
        }
      />
      <WorkspaceKpiCard
        label="Running MTM Profit/Loss"
        value={formatUsdWithSymbol(metrics.totalPnl, { signed: true })}
        accent
        footer={<span>Auto calculating Delta MTM</span>}
      />
    </div>
  );
}
