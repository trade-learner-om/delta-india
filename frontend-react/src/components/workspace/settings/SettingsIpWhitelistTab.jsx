import { cardInner, textMuted, accentLabel, secondaryButton } from "../../../utils/workspace/workspaceClasses";

export default function SettingsIpWhitelistTab({ serverIp, serverIpError, onCopy, ipCopied }) {
  return (
    <div className="space-y-4">
      <div className={`${cardInner("p-6 text-center space-y-4")}`}>
        <p className={`text-xs uppercase tracking-widest font-semibold ${textMuted()}`}>Active Workstation Proxy IP</p>
        {serverIp ? (
          <div className={`text-4xl font-mono font-extrabold tracking-wider ${accentLabel()}`}>{serverIp}</div>
        ) : (
          <div className={`text-sm ${textMuted()}`}>{serverIpError || "Loading server IP..."}</div>
        )}
        <p className={`text-xs max-w-md mx-auto leading-relaxed ${textMuted()}`}>
          Delta Exchange India API keys require whitelisting the deployment host IP. Copy this address into your Delta API profile to allow signed orders.
        </p>
        <button
          type="button"
          onClick={onCopy}
          disabled={!serverIp}
          className={secondaryButton("disabled:opacity-50")}
        >
          {ipCopied ? "Copied" : "Copy Server IP Address"}
        </button>
      </div>
    </div>
  );
}
