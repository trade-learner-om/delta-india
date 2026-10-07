export default function WorkspaceProgressBar({ value, className = "" }) {
  const pct = Math.max(0, Math.min(100, Number(value) || 0));
  return (
    <div className={`h-1 bg-slate-200 dark:bg-zinc-950 rounded-full overflow-hidden ${className}`.trim()}>
      <div className="h-full bg-lime-500 dark:bg-lime-400 transition-all duration-300" style={{ width: `${pct}%` }} />
    </div>
  );
}
