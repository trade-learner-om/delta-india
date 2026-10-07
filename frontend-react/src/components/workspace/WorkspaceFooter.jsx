import CryptoBridgeLogo from "./CryptoBridgeLogo";
import { textMuted, textBody } from "../../utils/workspace/workspaceClasses";

export default function WorkspaceFooter({ liveStatus = "disconnected" }) {
  const wsOk = liveStatus === "connected" || liveStatus === "reconnecting";
  const now = new Date().toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <footer className={`bg-slate-100 dark:bg-zinc-900 border-t border-slate-200 dark:border-zinc-800 px-6 py-4 text-xs ${textMuted()} flex flex-col md:flex-row justify-between items-center gap-3 font-mono`}>
      <div className="flex items-center gap-3">
        <CryptoBridgeLogo size={16} iconOnly />
        <span>
          Workstation timezone: <strong className={textBody()}>IST (UTC+5:30)</strong>
        </span>
        <span className="mx-2 text-slate-300 dark:text-zinc-700">|</span>
        <span>
          Last Server State Log: <strong className={textBody()}>{now}</strong>
        </span>
      </div>
      <div className="flex items-center gap-4">
        <span className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full inline-block ${wsOk ? "bg-lime-400 animate-pulse" : "bg-red-500"}`} />
          Delta India WS Node: <strong className={textBody()}>{wsOk ? "OK" : "DOWN"}</strong>
        </span>
        <span className="flex items-center gap-1.5">
          MongoDB async connect: <strong className="text-lime-600 dark:text-lime-400 font-bold">ACTIVE</strong>
        </span>
      </div>
    </footer>
  );
}
