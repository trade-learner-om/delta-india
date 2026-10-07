import WorkspaceCard from "./WorkspaceCard";
import { pnlColorClass } from "../../utils/workspace/workspaceFormatters";
import { textMuted } from "../../utils/workspace/workspaceClasses";

export default function WorkspaceKpiCard({
  label,
  value,
  footer,
  valueClassName,
  accent = false,
}) {
  const valueClass = valueClassName || "text-slate-900 dark:text-zinc-100";
  return (
    <WorkspaceCard className="relative overflow-hidden">
      <p className={`text-xs font-bold uppercase tracking-widest ${textMuted()}`}>{label}</p>
      <p className={`text-2xl font-mono font-extrabold mt-1.5 ${accent ? pnlColorClass(value) : valueClass}`}>
        {value}
      </p>
      {footer ? <div className={`text-[10px] mt-3 ${textMuted()}`}>{footer}</div> : null}
    </WorkspaceCard>
  );
}
