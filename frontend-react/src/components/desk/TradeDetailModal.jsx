import { useEffect, useRef, useState } from "react";
import { apiBlob } from "../../api";
import { formatIst, formatRealizedR, ledgerField, ledgerMuted, ledgerPanel, money, pnlClass, realizedRr } from "./deskFormat";

const CHART_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);

function chartFileFromClipboard(clipboard) {
  const items = Array.from(clipboard?.items || []);
  const image = items.find((item) => String(item.type || "").startsWith("image/"));
  if (image) return image.getAsFile();
  return Array.from(clipboard?.files || []).find((file) => String(file.type || "").startsWith("image/")) || null;
}

export default function TradeDetailModal({ token, trade, onClose, onSaved, onUploadChart }) {
  const [setup, setSetup] = useState(trade?.setup || "");
  const [reason, setReason] = useState(trade?.reason || "");
  const [stop, setStop] = useState(trade?.stopLoss ?? "");
  const [chartUrl, setChartUrl] = useState("");
  const [chartFile, setChartFile] = useState(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const localUrl = useRef("");
  const panelRef = useRef(null);
  const locked = Boolean(trade?.locked);
  const saved = Boolean(trade?.id && trade?.savedAt);

  useEffect(() => {
    let url = "";
    let cancelled = false;
    if (token && trade?.id && trade?.hasChart && !localUrl.current) {
      apiBlob(`/journal/${trade.id}/chart`, token)
        .then((blob) => {
          if (cancelled || localUrl.current) return;
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

  useEffect(() => () => {
    if (localUrl.current) URL.revokeObjectURL(localUrl.current);
  }, []);

  useEffect(() => {
    panelRef.current?.focus();
  }, []);

  if (!trade) return null;

  const showChartFile = (file) => {
    if (localUrl.current) URL.revokeObjectURL(localUrl.current);
    const url = URL.createObjectURL(file);
    localUrl.current = url;
    setChartUrl(url);
  };

  const acceptChart = async (file) => {
    if (locked || !file) return;
    const type = String(file.type || "").toLowerCase();
    if (!CHART_TYPES.has(type)) {
      setError("Chart snapshot must be a PNG, JPEG, or WebP image.");
      return;
    }
    if (file.size > 5_000_000) {
      setError("Chart snapshot must be under 5 MB.");
      return;
    }
    setError("");
    showChartFile(file);
    if (trade.id) {
      setPending(true);
      try {
        await onUploadChart?.(trade, file);
        setChartFile(null);
      } catch (err) {
        setError(err.message || "Chart snapshot was not saved.");
      } finally {
        setPending(false);
      }
      return;
    }
    setChartFile(file);
  };

  const pasteChart = (event) => {
    if (locked) return;
    const file = chartFileFromClipboard(event.clipboardData);
    if (!file) return;
    event.preventDefault();
    acceptChart(file);
  };

  const save = async () => {
    setPending(true);
    setError("");
    try {
      const stopValue = stop === "" || stop == null ? null : Number(stop);
      const savedEntry = await onSaved({
        ...trade,
        setup,
        reason,
        stopLoss: Number.isFinite(stopValue) && stopValue > 0 ? stopValue : null,
      });
      const entry = savedEntry?.id ? savedEntry : trade;
      if (chartFile && entry?.id) {
        await onUploadChart?.(entry, chartFile);
      }
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
        ref={panelRef}
        tabIndex={-1}
        className={`max-h-[90vh] w-full max-w-xl overflow-y-auto p-6 shadow-2xl outline-none ${ledgerPanel}`}
        onClick={(event) => event.stopPropagation()}
        onPaste={pasteChart}
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
            ["Net P/L", money(trade.netPnl)],
            ["Entry time", formatIst(trade.entryTimeIst)],
            ["Exit time", formatIst(trade.exitTimeIst)],
          ].map(([label, value]) => (
            <div key={label} className={`rounded-xl px-3 py-2 ${ledgerPanel}`}>
              <dt className={`text-[11px] uppercase tracking-wider ${ledgerMuted}`}>{label}</dt>
              <dd className={label === "Net P/L" ? `mt-1 ${pnlClass(trade.netPnl)}` : "mt-1"}>{value}</dd>
            </div>
          ))}
          <div className={`rounded-xl px-3 py-2 ${ledgerPanel}`}>
            <dt className={`text-[11px] uppercase tracking-wider ${ledgerMuted}`}>Stop</dt>
            {locked ? (
              <dd className="mt-1">{trade.stopLoss ?? "—"}</dd>
            ) : (
              <input
                className={`mt-1 ${ledgerField}`}
                inputMode="decimal"
                value={stop}
                onChange={(event) => setStop(event.target.value)}
              />
            )}
          </div>
          <div className={`rounded-xl px-3 py-2 ${ledgerPanel}`}>
            <dt className={`text-[11px] uppercase tracking-wider ${ledgerMuted}`}>R</dt>
            <dd className="mt-1">{formatRealizedR(realizedRr(trade.side, trade.entry, stop, trade.exit))}</dd>
          </div>
        </dl>
        {chartUrl ? <img src={chartUrl} alt="Chart snapshot" className="mt-4 w-full rounded-xl" /> : null}
        {locked ? null : (
          <div className="mt-4">
            <label className="inline-flex cursor-pointer rounded-full border border-[var(--ledger-accent)] px-4 py-2 text-sm text-[var(--ledger-accent)]">
              Upload chart
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  acceptChart(file);
                }}
              />
            </label>
            <p className={`mt-2 text-sm ${ledgerMuted}`}>Or paste an image from the clipboard.</p>
          </div>
        )}
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
