import { field, fieldLabel, formLabel, formHint } from "../../utils/workspace/workspaceClasses";

export function WorkspaceField({ label, children, hint }) {
  return (
    <label className="block">
      {label ? <span className={fieldLabel()}>{label}</span> : null}
      {children}
      {hint ? <span className={formHint()}>{hint}</span> : null}
    </label>
  );
}

export function WorkspaceFormField({ label, hint, children }) {
  return (
    <label className={formLabel()}>
      {label}
      {children}
      {hint ? <span className={formHint()}>{hint}</span> : null}
    </label>
  );
}

export function WorkspaceInput({ className = "", ...props }) {
  return <input className={`${field()} ${className}`.trim()} {...props} />;
}

export function WorkspaceSelect({ className = "", children, ...props }) {
  return (
    <select className={`${field()} font-sans ${className}`.trim()} {...props}>
      {children}
    </select>
  );
}

export function WorkspaceToggle({ checked, onChange, label }) {
  return (
    <label className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-zinc-300 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 rounded border-slate-300 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-indigo-600 dark:text-lime-400 focus:ring-indigo-500 dark:focus:ring-lime-400"
      />
      {label}
    </label>
  );
}
