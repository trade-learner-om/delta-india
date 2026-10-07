import { textBody, textMuted } from "../../utils/workspace/workspaceClasses";

export default function WorkspaceToast({ message, type = "success" }) {
  if (!message) return null;

  const isError = type === "error";
  const accent = isError
    ? "border-rose-500 dark:border-rose-400"
    : "border-lime-500 dark:border-lime-400";
  const label = isError ? "Error" : "Workspace Broker Signal";

  return (
    <div
      className={`fixed bottom-6 right-6 z-50 max-w-sm bg-white dark:bg-zinc-900 border-l-4 ${accent} text-slate-900 dark:text-zinc-100 px-4 py-3 rounded-lg shadow-2xl flex items-start gap-2.5 animate-slide-in`}
    >
      <div className="flex-1">
        <p className={`text-[10px] font-bold uppercase tracking-widest ${textMuted()}`}>{label}</p>
        <p className={`text-sm font-semibold mt-0.5 ${textBody()}`}>{message}</p>
      </div>
    </div>
  );
}
