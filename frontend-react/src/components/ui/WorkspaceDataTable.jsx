import { card, textMuted } from "../../utils/workspace/workspaceClasses";

export default function WorkspaceDataTable({ title, badge, children, emptyMessage, bodyClassName }) {
  return (
    <div className={card("overflow-hidden shadow-md")}>
      {title ? (
        <div className="p-4 bg-slate-50 dark:bg-zinc-950 border-b border-slate-200 dark:border-zinc-800 flex justify-between items-center">
          <h3 className={`text-xs font-bold uppercase tracking-wider ${textMuted()}`}>{title}</h3>
          {badge ? (
            <span className="px-2 py-0.5 bg-slate-200 dark:bg-zinc-850 text-[10px] text-slate-600 dark:text-zinc-400 rounded-md">
              {badge}
            </span>
          ) : null}
        </div>
      ) : null}
      {emptyMessage && !children ? (
        <div className={`p-12 text-center text-xs ${textMuted()}`}>{emptyMessage}</div>
      ) : (
        <div className={bodyClassName || "overflow-x-auto"}>{children}</div>
      )}
    </div>
  );
}

export function WorkspaceTable({ children }) {
  return <table className="w-full text-left text-xs font-mono">{children}</table>;
}

export function WorkspaceTableHead({ children }) {
  return (
    <thead>
      <tr className="border-b border-slate-200 dark:border-zinc-850 bg-slate-50 dark:bg-zinc-900 text-slate-500 dark:text-zinc-500 uppercase tracking-widest text-[9px] font-bold">
        {children}
      </tr>
    </thead>
  );
}

export function WorkspaceTableBody({ children }) {
  return <tbody className="divide-y divide-slate-100 dark:divide-zinc-850">{children}</tbody>;
}
