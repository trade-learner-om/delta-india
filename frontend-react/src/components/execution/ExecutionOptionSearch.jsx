import { useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import { WorkspaceField, WorkspaceInput } from "../ui/WorkspaceField";
import { cardInner, textMuted } from "../../utils/workspace/workspaceClasses";
import { formatOptionPrice, readOptionLivePrice } from "./executionUtils";

function formatStrike(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return numeric.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

export default function ExecutionOptionSearch({ token, livePrices, selected, onSelect }) {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return undefined;
    const handle = window.setTimeout(async () => {
      setLoading(true);
      setError("");
      try {
        const data = await api(`/execution/options/search?q=${encodeURIComponent(query)}`, { token });
        setOptions(data.options || []);
      } catch (err) {
        setError(err.message || "Search failed.");
        setOptions([]);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => window.clearTimeout(handle);
  }, [token, query]);

  const selectedId = selected?.symbol || "";

  const rows = useMemo(() => options, [options]);

  return (
    <div className="space-y-3">
      <WorkspaceField label="Search options (BTC / ETH)">
        <WorkspaceInput
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Strike, symbol, CE, PE…"
        />
      </WorkspaceField>
      {error ? <p className="text-xs text-red-600 dark:text-red-400">{error}</p> : null}
      <div className={`${cardInner()} max-h-56 overflow-y-auto divide-y divide-slate-200 dark:divide-zinc-800`}>
        {loading && !rows.length ? (
          <p className={`p-3 text-xs ${textMuted()}`}>Searching…</p>
        ) : null}
        {!loading && !rows.length ? (
          <p className={`p-3 text-xs ${textMuted()}`}>No matching options.</p>
        ) : null}
        {rows.map((row) => {
          const active = selectedId === row.symbol;
          const livePrice = readOptionLivePrice(livePrices, row.symbol);
          return (
            <button
              key={row.symbol}
              type="button"
              onClick={() => onSelect(row)}
              className={`w-full text-left px-3 py-2 text-xs transition ${
                active
                  ? "bg-lime-400/20 text-slate-900 dark:text-lime-300"
                  : "hover:bg-slate-100 dark:hover:bg-zinc-900"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="font-mono font-semibold truncate">{row.symbol}</span>
                <span className="shrink-0 font-mono font-semibold text-lime-700 dark:text-lime-400">
                  {livePrice != null ? `$${formatOptionPrice(livePrice)}` : "—"}
                </span>
              </div>
              <div className={`mt-0.5 flex items-center justify-between gap-2 ${textMuted()}`}>
                <span>
                  {row.underlying} · strike {formatStrike(row.strikePrice)} · {row.optionType}
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
