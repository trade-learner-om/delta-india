import { ledgerMuted } from "./deskFormat";

function activeClass(tone, id, selected) {
  if (!selected) return ledgerMuted;
  if (tone === "side" && id === "BUY") return "bg-[var(--ledger-profit)] text-white shadow-lg shadow-emerald-500/20";
  if (tone === "side" && id === "SELL") return "bg-[var(--ledger-loss)] text-white shadow-lg shadow-rose-500/20";
  return "bg-[var(--ledger-accent)] text-white";
}

export default function ChoiceSwitch({ value, options, onChange, label, tone }) {
  return (
    <div>
      {label ? <p className="mb-1 text-sm">{label}</p> : null}
      <div className="flex rounded-full border border-[var(--ledger-border)] bg-[var(--ledger-canvas)] p-1">
        {options.map(([id, text]) => (
          <button
            key={id}
            type="button"
            onClick={() => onChange(id)}
            className={`flex-1 rounded-full px-3 py-1.5 text-sm transition ${activeClass(tone, id, value === id)}`}
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}
