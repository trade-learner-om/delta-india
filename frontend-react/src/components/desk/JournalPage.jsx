import { useEffect, useState } from "react";
import { api, apiUpload } from "../../api";
import { formatIst, money, pnlClass } from "./deskFormat";
import TradeDetailModal from "./TradeDetailModal";

export default function JournalPage({ token, onNotify, onChanged }) {
  const [saved, setSaved] = useState([]);
  const [recent, setRecent] = useState([]);
  const [open, setOpen] = useState(null);

  const load = async () => {
    const [savedData, recentData] = await Promise.all([
      api("/journal", { token }),
      api("/journal/recent", { token }),
    ]);
    setSaved(savedData.entries || []);
    setRecent(recentData.trades || []);
  };

  useEffect(() => {
    if (!token) return;
    load().catch((err) => onNotify("error", err.message || "Journal could not load."));
  }, [token]);

  const saveTrade = async (trade) => {
    if (trade.savedAt && trade.id) {
      await api(`/journal/${trade.id}`, {
        method: "PATCH",
        token,
        body: { setup: trade.setup, reason: trade.reason },
      });
    } else {
      await api("/journal", {
        method: "POST",
        token,
        body: { sourceTradeId: trade.sourceTradeId, setup: trade.setup, reason: trade.reason },
      });
    }
    onNotify("success", "Journal saved.");
    await load();
    onChanged?.();
  };

  const upload = async (trade, file) => {
    if (!trade?.id || !file) return;
    await apiUpload(`/journal/${trade.id}/chart`, token, file);
    onNotify("success", "Chart snapshot saved.");
    await load();
  };

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-white/10 bg-[#1e2128] p-4">
        <h1 className="text-xl">Recent broker trades</h1>
        <p className="mt-1 text-sm text-[#9a958c]">Times are shown in IST. Save a trade to keep the setup and the reason.</p>
        <div className="mt-4 divide-y divide-white/5">
          {recent.length === 0 ? <p className="py-3 text-sm text-[#9a958c]">No unsaved broker trades.</p> : null}
          {recent.map((trade) => (
            <button key={trade.sourceTradeId} type="button" onClick={() => setOpen(trade)} className="flex w-full items-center justify-between py-3 text-left">
              <span>
                <span className="block">{trade.symbol}</span>
                <span className="text-xs text-[#9a958c]">{trade.accountName} · {formatIst(trade.exitTimeIst)}</span>
              </span>
              <span className={pnlClass(trade.netPnl)}>{money(trade.netPnl)}</span>
            </button>
          ))}
        </div>
      </section>
      <section className="rounded-2xl border border-white/10 bg-[#1e2128] p-4">
        <h2 className="text-sm text-[#9a958c]">Saved journal</h2>
        <div className="mt-3 divide-y divide-white/5">
          {saved.map((trade) => (
            <div key={trade.id} className="flex items-center justify-between gap-3 py-3">
              <button type="button" onClick={() => setOpen(trade)} className="text-left">
                <span className="block">{trade.symbol}</span>
                <span className="text-xs text-[#9a958c]">{trade.accountName} · {trade.locked ? "Locked" : "Editable"}</span>
              </button>
              <label className="cursor-pointer text-xs text-[#8eafc4]">
                Chart
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  className="hidden"
                  disabled={trade.locked}
                  onChange={(event) => upload(trade, event.target.files?.[0]).catch((err) => onNotify("error", err.message))}
                />
              </label>
            </div>
          ))}
        </div>
      </section>
      {open ? <TradeDetailModal token={token} trade={open} onClose={() => setOpen(null)} onSaved={saveTrade} /> : null}
    </div>
  );
}
