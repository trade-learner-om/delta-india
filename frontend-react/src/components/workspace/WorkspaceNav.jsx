import { buildNavItems } from "../../utils/workspace/workspaceNav";
import { navShell, textMuted } from "../../utils/workspace/workspaceClasses";

function badgeClass(tone, active) {
  if (active) {
    return "px-1.5 py-0.5 bg-zinc-950/15 text-zinc-950 border border-zinc-950/30 rounded text-[9px] font-mono font-bold uppercase tracking-tight";
  }
  return `px-1.5 py-0.5 rounded-md text-[9px] font-bold ${
    active ? "bg-slate-200 dark:bg-zinc-950 text-lime-600 dark:text-lime-400" : "bg-slate-100 dark:bg-zinc-800 text-slate-600 dark:text-zinc-300"
  }`;
}

export default function WorkspaceNav({
  currentPage,
  onPageChange,
  positionCount = 0,
  executionCount = 0,
  stOptionsCount = 0,
  cascadeStarCount = 0,
}) {
  const items = buildNavItems({ positionCount, executionCount, stOptionsCount, cascadeStarCount });

  return (
    <nav className={navShell()}>
      {items.map((item) => {
        const active = currentPage === item.id;
        const Icon = item.icon;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onPageChange(item.id)}
            className={`px-4 py-2 rounded-lg text-xs font-bold tracking-wide transition flex items-center gap-2 whitespace-nowrap ${
              active
                ? "bg-lime-400 text-zinc-950 font-extrabold shadow"
                : `${textMuted()} hover:text-slate-800 dark:hover:text-zinc-200 hover:bg-slate-200 dark:hover:bg-zinc-800`
            }`}
          >
            {Icon ? <Icon className="w-4 h-4" /> : null}
            {item.label}
            {item.badge ? (
              <span className={badgeClass(item.badgeTone, active)}>{item.badge}</span>
            ) : null}
          </button>
        );
      })}
    </nav>
  );
}
