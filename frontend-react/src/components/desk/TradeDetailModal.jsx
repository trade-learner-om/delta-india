import { useEffect, useState } from "react";
import { apiBlob } from "../../api";
import { formatIst, ledgerField, ledgerMuted, ledgerPanel, money, pnlClass } from "./deskFormat";

export default function TradeDetailModal({ token, trade, onClose, onSaved }) {
  const [setup, setSetup] = useState(trade?.setup || "");
  const [reason, setReason] = useState(trade?.reason || "");
  const [chartUrl, setChartUrl] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const locked = Boolean(trade?.locked);
  const saved = Boolean(trade?.id && trade?.savedAt);

  useEffect(() => {
    let url = "";
    let cancelled = false;
    if (token && trade?.id && trade?.hasChart) {
      apiBlob(`/journal/${trade.id}/chart`, token)
        .then((blob) => {
          if (cancelled) return;
          url = URL.createObjectURL(blob);
          setChartUrl(url);
        })
        .catch(() => {});
    }
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [token, trade]);

  if (!trade) return null;

  const save = async () => {
    setPending(true);
    setError("");
    try {
      await onSaved({ ...trade, setup, reason });
      onClose();
    } catch (err) {
      setError(err.message || "Could not save this trade.");
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className={`max-h-[90vh] w-full max-w-xl overflow-y-auto p-6 shadow-2xl ${ledgerPanel}`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className={`text-xs uppercase tracking-[0.16em] ${ledgerMuted}`}>{trade.venue}</p>
            <h2 className="mt-1 text-2xl">{trade.symbol}</h2>
            <p className={`text-sm ${ledgerMuted}`}>{trade.accountName}</p>
          </div>
          <button type="button" className="text-sm text-[var(--ledger-accent)]" onClick={onClose}>Close</button>
        </div>
        <dl className="mt-6 grid grid-cols-2 gap-3 text-sm">
          {[
            ["Entry", trade.entry],
            ["Exit", trade.exit],
            ["Quantity", trade.quantity],
            ["Stop", trade.stopLoss ?? "—"],
            ["R", trade.rr ?? "—"],
            ["Net P/L", money(trade.netPnl)],
            ["Entry time", formatIst(trade.entryTimeIst)],
            ["Exit time", formatIst(trade.exitTimeIst)],
          ].map(([label, value]) => (
            <div key={label} className={`rounded-xl px-3 py-2 ${ledgerPanel}`}>
              <dt className={`text-[11px] uppercase tracking-wider ${ledgerMuted}`}>{label}</dt>
              <dd className={label === "Net P/L" ? `mt-1 ${pnlClass(trade.netPnl)}` : "mt-1"}>{value}</dd>
            </div>
          ))}
        </dl>
        {chartUrl ? <img src={chartUrl} alt="Chart snapshot" className="mt-4 w-full rounded-xl" /> : null}
        <label className="mt-4 block text-sm">
          Trade setup
          <input
            className={`mt-1 ${ledgerField}`}
            value={setup}
            disabled={locked}
            onChange={(event) => setSetup(event.target.value)}
          />
        </label>
        <label className="mt-3 block text-sm">
          Why this trade was taken
          <textarea
            className={`mt-1 min-h-24 ${ledgerField}`}
            value={reason}
            disabled={locked}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        {error ? <p className="mt-3 text-sm text-[var(--ledger-loss)]">{error}</p> : null}
        {locked ? (
          <p className={`mt-4 text-sm ${ledgerMuted}`}>This entry has been locked for 24 hours.</p>
        ) : (
          <button
            type="button"
            disabled={pending}
            onClick={save}
            className="mt-4 rounded-full bg-[var(--ledger-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {pending ? "Saving" : saved ? "Update notes" : "Save to journal"}
          </button>
        )}
      </div>
    </div>
  );
}
