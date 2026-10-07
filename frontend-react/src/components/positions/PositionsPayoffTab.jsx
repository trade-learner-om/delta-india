import PayoffChart from "./PayoffChart";
import WorkspaceCard from "../ui/WorkspaceCard";
import { textHeading, textMuted } from "../../utils/workspace/workspaceClasses";

export default function PositionsPayoffTab({ payoff, selectedCount }) {
  if (!selectedCount) {
    return (
      <WorkspaceCard>
        <p className={`text-xs ${textMuted()}`}>
          Select open positions on the Open tab, then return here to view payoff.
        </p>
      </WorkspaceCard>
    );
  }
  if (!payoff) {
    return (
      <WorkspaceCard>
        <p className={`text-xs ${textMuted()}`}>
          Payoff is available when selected positions share the same underlying.
        </p>
      </WorkspaceCard>
    );
  }
  return (
    <WorkspaceCard className="space-y-4">
      <h3 className={`text-xs font-bold uppercase tracking-wider ${textHeading()}`}>Payoff Simulator</h3>
      <PayoffChart payoff={payoff} spot={payoff.spot} loading={false} title={payoff.title || "Selected positions payoff"} />
    </WorkspaceCard>
  );
}
