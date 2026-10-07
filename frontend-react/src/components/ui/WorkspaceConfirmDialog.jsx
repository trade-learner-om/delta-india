import { modalPanel, secondaryButton, primaryButton, dangerButton, textHeading, textBody } from "../../utils/workspace/workspaceClasses";

export default function WorkspaceConfirmDialog({
  open,
  title,
  children,
  confirmLabel = "Confirm",
  onConfirm,
  onCancel,
  danger = false,
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 dark:bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className={modalPanel("max-w-md w-full overflow-hidden animate-scale-in")}>
        <div className="px-6 py-5 border-b border-slate-200 dark:border-zinc-800">
          <h3 className={`text-base font-bold uppercase tracking-wider ${textHeading()}`}>{title}</h3>
        </div>
        <div className={`p-6 space-y-4 text-sm ${textBody()}`}>{children}</div>
        <div className="bg-slate-50 dark:bg-zinc-950 px-6 py-4 border-t border-slate-200 dark:border-zinc-800 flex justify-end gap-3">
          <button type="button" onClick={onCancel} className={secondaryButton()}>
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={danger ? dangerButton() : primaryButton()}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
