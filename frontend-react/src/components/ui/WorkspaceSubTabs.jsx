import { subTab, subTabBar } from "../../utils/workspace/workspaceClasses";

export default function WorkspaceSubTabs({ tabs, activeId, onChange, className = "" }) {
  return (
    <div className={`${subTabBar()} ${className}`.trim()}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onChange(tab.id)}
          className={`${subTab(activeId === tab.id)} flex-1 md:flex-none whitespace-nowrap`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
