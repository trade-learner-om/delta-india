import WorkspaceSubTabs from "../ui/WorkspaceSubTabs";

export default function PositionsSubTabs({ activeId, onChange, openCount, pastCount }) {
  return (
    <WorkspaceSubTabs
      activeId={activeId}
      onChange={onChange}
      tabs={[
        { id: "open", label: `Open Position Desk (${openCount})` },
        { id: "history", label: `Past Orders (${pastCount})` },
        { id: "payoff", label: "Payoff Simulator" },
      ]}
    />
  );
}
