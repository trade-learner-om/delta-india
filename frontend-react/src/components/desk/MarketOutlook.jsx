import { useEffect, useRef, useState } from "react";
import { AlertTriangle, BrainCircuit, ChevronLeft, ChevronRight, Coins, Globe, RotateCw } from "lucide-react";
import { api } from "../../api";
import CoinIcon from "../CoinIcon";
import { livePriceFromTick, lookupLiveTick } from "../../utils/pricePrecision";
import { formatPrice, ledgerMuted, ledgerPanel } from "./deskFormat";
import PriceFlashTicker from "./PriceFlashTicker";

export const CAUTION = "Caution: These probabilities are AI-generated market simulations for educational purposes only. Do not initiate trades based on these results.";

const HORIZONS = [
  ["horizon_1h", "1H"],
  ["horizon_4h", "4H"],
  ["horizon_24h", "24H"],
];

const TILES = [
  {
    title: "Crypto Market Overview",
    venue: "crypto",
    Icon: Coins,
    symbols: ["BTCUSD", "ETHUSD", "SOLUSD"],
  },
  {
    title: "Forex Market Overview",
    venue: "forex",
    Icon: Globe,
    symbols: ["XAUUSD", "EURUSD", "AUDUSD", "GBPUSD", "GBPJPY", "EURJPY"],
  },
];

function pagesOf(symbols) {
  const pages = [];
  for (let index = 0; index < symbols.length; index += 2) {
    pages.push(symbols.slice(index, index + 2));
  }
  return pages;
}

function requestOrder() {
  const first = TILES.flatMap((tile) => pagesOf(tile.symbols)[0] || []);
  const rest = TILES.flatMap((tile) => tile.symbols).filter((symbol) => !first.includes(symbol));
  return [...first, ...rest];
}

export default function MarketOutlook({ token, livePrices, forecasts }) {
  const [rows, setRows] = useState({});
  const [pages, setPages] = useState({ crypto: 0, forex: 0 });

  useEffect(() => {
    if (!forecasts) return;
    setRows((current) => {
      const next = { ...current };
      Object.entries(forecasts).forEach(([symbol, payload]) => {
        if (payload?.status === "error") {
          next[symbol] = { status: "error", error: payload.error || "Forecast unavailable." };
          return;
        }
        if (payload?.horizon_1h || payload?.status === "ready") {
          next[symbol] = { status: "ready", data: payload };
        }
      });
      return next;
    });
  }, [forecasts]);

  useEffect(() => {
    if (!token) return undefined;
    let cancelled = false;
    const symbols = requestOrder();
    setRows((current) => {
      const next = { ...current };
      symbols.forEach((symbol) => {
        if (!next[symbol]) next[symbol] = { status: "loading" };
      });
      return next;
    });
    TILES.forEach((tile) => {
      tile.symbols.forEach((symbol) => {
        api("/market/subscribe", { method: "POST", token, body: { venue: tile.venue, symbol } }).catch(() => {});
      });
    });
    (async () => {
      for (const symbol of symbols) {
        if (cancelled) return;
        try {
          const data = await api(`/ai-predictions?symbol=${encodeURIComponent(symbol)}`, { token });
          if (cancelled || data?.status === "pending") continue;
          if (data?.horizon_1h) {
            setRows((current) => ({ ...current, [symbol]: { status: "ready", data } }));
          }
        } catch (err) {
          if (!cancelled) {
            setRows((current) => ({ ...current, [symbol]: { status: "error", error: err.message || "Forecast unavailable." } }));
          }
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <div className="grid items-stretch gap-4 xl:grid-cols-2">
      {TILES.map((tile) => (
        <ForecastTile
          key={tile.venue}
          tile={tile}
          page={pages[tile.venue] || 0}
          onPage={(next) => setPages((current) => ({ ...current, [tile.venue]: next }))}
          rows={rows}
          livePrices={livePrices}
        />
      ))}
    </div>
  );
}

function ForecastTile({ tile, page, onPage, rows, livePrices }) {
  const groups = pagesOf(tile.symbols);
  const index = Math.min(page, groups.length - 1);
  const visible = groups[index] || [];
  return (
    <section className={`flex h-full flex-col gap-3 p-4 ${ledgerPanel}`}>
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <tile.Icon size={16} />
        {tile.title}
      </h2>
      <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-200">
        <AlertTriangle size={14} className="shrink-0" />
        <p>{CAUTION}</p>
      </div>
      <div className="grid min-h-[17rem] flex-1 grid-rows-2 gap-3">
        {visible.map((symbol) => (
          <ForecastRow
            key={symbol}
            symbol={symbol}
            row={rows[symbol]}
            livePrices={livePrices}
            onRetry={() => retryForecast(token, symbol, setRows)}
          />
        ))}
        {visible.length < 2 ? <div aria-hidden="true" /> : null}
      </div>
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          aria-label={`Previous ${tile.title} page`}
          disabled={index === 0}
          onClick={() => onPage(index - 1)}
          className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-[var(--ledger-border)] disabled:opacity-40"
        >
          <ChevronLeft size={14} />
        </button>
        <div className="flex items-center gap-1.5">
          {groups.map((group, dot) => (
            <button
              key={group.join("-")}
              type="button"
              aria-label={`${tile.title} page ${dot + 1}`}
              onClick={() => onPage(dot)}
              className={`h-2 w-2 rounded-full ${dot === index ? "bg-[var(--ledger-accent)]" : "border border-[var(--ledger-muted)] bg-transparent"}`}
            />
          ))}
        </div>
        <button
          type="button"
          aria-label={`Next ${tile.title} page`}
          disabled={index >= groups.length - 1}
          onClick={() => onPage(index + 1)}
          className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-[var(--ledger-border)] disabled:opacity-40"
        >
          <ChevronRight size={14} />
        </button>
      </div>
    </section>
  );
}

function retryForecast(token, symbol, setRows) {
  setRows((current) => ({ ...current, [symbol]: { status: "loading" } }));
  api(`/ai-predictions?symbol=${encodeURIComponent(symbol)}&refresh=1`, { token })
    .then((data) => {
      if (data?.status === "pending") return;
      if (data?.horizon_1h) {
        setRows((current) => ({ ...current, [symbol]: { status: "ready", data } }));
      }
    })
    .catch((err) => {
      setRows((current) => ({ ...current, [symbol]: { status: "error", error: err.message || "Forecast unavailable." } }));
    });
}

function ForecastRow({ symbol, row, livePrices, onRetry }) {
  const price = livePriceFromTick(lookupLiveTick(livePrices, symbol));
  return (
    <article className="rounded-xl border border-[var(--ledger-border)] p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="inline-flex items-center gap-2 text-sm font-semibold">
          <CoinIcon coin={symbol} size={18} />
          {symbol}
          <BrainCircuit size={14} className={ledgerMuted} />
        </p>
        <div className="flex items-center gap-2">
          <PriceFlashTicker value={price} className={`text-sm ${ledgerMuted}`}>
            {price == null ? "—" : formatPrice(price)}
          </PriceFlashTicker>
          <button
            type="button"
            aria-label="Retry"
            onClick={onRetry}
            className={`inline-flex h-5 w-5 items-center justify-center rounded-full border border-[var(--ledger-border)] ${ledgerMuted}`}
          >
            <RotateCw size={12} />
          </button>
          <RationaleTip text={row?.status === "ready" ? row.data?.technical_rationale : ""} />
        </div>
      </div>
      {row?.status === "loading" || !row ? <p className={`mt-2 text-xs ${ledgerMuted}`}>Loading forecast…</p> : null}
      {row?.status === "error" ? <p className="mt-2 text-xs text-[var(--ledger-loss)]">{row.error}</p> : null}
      {row?.status === "ready" ? (
        <div className="mt-3 space-y-2">
          {HORIZONS.map(([key, label]) => (
            <HorizonBar key={key} label={label} horizon={row.data?.[key]} />
          ))}
        </div>
      ) : null}
    </article>
  );
}

function RationaleTip({ text }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = (event) => {
      if (!ref.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        aria-label="Show forecast rationale"
        onClick={() => setOpen((current) => !current)}
        className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-[var(--ledger-border)] text-[11px] font-semibold"
      >
        ?
      </button>
      {open ? (
        <div
          role="tooltip"
          className="absolute right-0 z-20 mt-1 w-64 rounded-lg border border-[var(--ledger-border)] bg-[var(--ledger-surface)] p-2 text-xs shadow-lg"
        >
          {text || "The rationale is not available yet."}
        </div>
      ) : null}
    </div>
  );
}

function HorizonBar({ label, horizon }) {
  const bullish = Number(horizon?.bullish);
  const bearish = Number(horizon?.bearish);
  const width = Number.isFinite(bullish) ? Math.max(0, Math.min(100, bullish)) : 0;
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2 text-[11px]">
        <span className={ledgerMuted}>{label}</span>
        <span className="flex gap-1">
          <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 font-semibold text-[var(--ledger-profit)]">
            Bull {Number.isFinite(bullish) ? bullish : "—"}%
          </span>
          <span className="rounded-full bg-rose-500/10 px-2 py-0.5 font-semibold text-[var(--ledger-loss)]">
            Bear {Number.isFinite(bearish) ? bearish : "—"}%
          </span>
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-[var(--ledger-canvas)]">
        <div className="h-full bg-[var(--ledger-profit)]" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}
