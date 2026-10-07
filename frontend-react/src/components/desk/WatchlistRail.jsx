import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { api } from "../../api";
import ChoiceSwitch from "./ChoiceSwitch";

const STORAGE_KEY = "ledger.watchlist.open";

export default function WatchlistRail({ token, watchlist, livePrices, onChanged, onNotify }) {
  const [open, setOpen] = useState(() => window.localStorage.getItem(STORAGE_KEY) !== "0");
  const [venue, setVenue] = useState("crypto");
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [message, setMessage] = useState("");

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, open ? "1" : "0");
  }, [open]);

  useEffect(() => {
    const text = query.trim();
    if (text.length < 2) {
      setSuggestions([]);
      setMessage("");
      return undefined;
    }
    let cancelled = false;
    const handle = window.setTimeout(() => {
      const params = new URLSearchParams({ venue, q: text });
      api(`/watchlist/suggest?${params}`, { token })
        .then((data) => {
          if (cancelled) return;
          const rows = data.suggestions || [];
          setSuggestions(rows);
          setMessage(data.message || (rows.length ? "" : "No matches"));
        })
        .catch((err) => {
          if (cancelled) return;
          setSuggestions([]);
          setMessage(err.message || "Suggestions are unavailable.");
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [query, venue, token]);

  const addSymbol = async (symbol) => {
    await api("/watchlist", { method: "POST", token, body: { venue, symbol } });
    setQuery("");
    setSuggestions([]);
    setMessage("");
    onChanged?.();
  };

  const removeSymbol = async (item) => {
    const params = new URLSearchParams({ venue: item.venue, symbol: item.symbol });
    await api(`/watchlist?${params}`, { method: "DELETE", token });
    onChanged?.();
  };

  const groups = {
    crypto: (watchlist || []).filter((item) => item.venue === "crypto"),
    forex: (watchlist || []).filter((item) => item.venue === "forex"),
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex h-full min-h-40 items-center justify-center rounded-2xl border border-white/10 bg-[#1e2128] px-2 py-4 text-xs uppercase tracking-[0.2em] text-[#9a958c] xl:w-11"
        style={{ writingMode: "vertical-rl" }}
      >
        Watchlist
      </button>
    );
  }

  return (
    <motion.aside
      initial={{ opacity: 0.6 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      className="rounded-2xl border border-white/10 bg-[#1e2128] p-4 xl:w-[280px]"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-sm text-[#9a958c]">Watchlist</h2>
        <button type="button" className="text-xs text-[#8eafc4]" onClick={() => setOpen(false)}>
          Collapse
        </button>
      </div>
      <div className="relative mt-3">
        <ChoiceSwitch
          value={venue}
          onChange={setVenue}
          options={[["crypto", "Crypto"], ["forex", "Forex"]]}
        />
        <input
          className="mt-2 w-full rounded-lg border border-white/10 bg-[#16181d] px-3 py-2 text-sm"
          placeholder="Search symbol"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        {suggestions.length || message ? (
          <div className="absolute z-10 mt-1 max-h-56 w-full overflow-y-auto rounded-xl border border-white/10 bg-[#16181d] shadow-xl">
            {message ? <p className="px-3 py-2 text-xs text-[#9a958c]">{message}</p> : null}
            {suggestions.map((item) => (
              <button
                key={`${item.venue}:${item.symbol}`}
                type="button"
                className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-white/5"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => addSymbol(item.symbol).catch((err) => onNotify("error", err.message))}
              >
                <span>{item.symbol}</span>
                <span className="text-[11px] uppercase tracking-wider text-[#8eafc4]">{item.venue}</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>
      {["crypto", "forex"].map((group) => (
        <div key={group} className="mt-4">
          <p className="text-[11px] uppercase tracking-[0.16em] text-[#8eafc4]">{group}</p>
          {groups[group].length === 0 ? <p className="mt-2 text-sm text-[#9a958c]">None yet</p> : null}
          {groups[group].map((item) => {
            const tick = livePrices?.[item.symbol] || {};
            const price = tick.price || tick.mark_price || tick.bid || tick.ask;
            return (
              <div key={item.id || item.symbol} className="mt-2 flex items-center justify-between gap-2 text-sm">
                <span>{item.symbol}</span>
                <span className="text-[#e6e2d8]">{price ?? "—"}</span>
                <button
                  type="button"
                  className="text-xs text-[#9a958c]"
                  onClick={() => removeSymbol(item).catch((err) => onNotify("error", err.message))}
                >
                  Remove
                </button>
              </div>
            );
          })}
        </div>
      ))}
    </motion.aside>
  );
}
