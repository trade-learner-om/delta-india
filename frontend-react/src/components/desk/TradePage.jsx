import { useEffect, useRef, useState } from "react";
import { ShieldAlert, SlidersHorizontal } from "lucide-react";
import { api } from "../../api";
import { livePriceFromTick, lookupLiveTick } from "../../utils/pricePrecision";
import ChoiceSwitch from "./ChoiceSwitch";
import PriceFlashTicker from "./PriceFlashTicker";
import { formatPrice, ledgerField, ledgerMuted, ledgerPanel, money, orderPriceMessage, rewardRisk, roundToStep, targetPriceFromR } from "./deskFormat";

const EMPTY = { venue: "crypto", symbol: "", side: "BUY", orderType: "LIMIT", entry: "", stopLoss: "", target: "" };

function RewardRiskBar({ ratio }) {
  const reward = Number(ratio);
  if (!Number.isFinite(reward) || reward <= 0) return null;
  const capped = Math.min(reward, 5);
  const riskWidth = (1 / (1 + capped)) * 100;
  return (
    <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-[var(--ledger-canvas)]">
      <div className="h-full bg-[var(--ledger-loss)]" style={{ width: `${riskWidth}%` }} />
      <div className="h-full bg-[var(--ledger-profit)]" style={{ width: `${100 - riskWidth}%` }} />
    </div>
  );
}

function limitR(value) {
  const match = String(value).match(/^\d*\.?\d{0,2}/);
  return match ? match[0] : "";
}

function accountForVenue(venue, deltaAccounts, mt5Accounts) {
  const list = venue === "forex" ? mt5Accounts : deltaAccounts;
  return (list || []).find((account) => account.selected) || ((list || []).length === 1 ? list[0] : null);
}

export default function TradePage({ token, deltaAccounts, mt5Accounts, livePrices, onNotify, onReload }) {
  const [form, setForm] = useState(EMPTY);
  const [preview, setPreview] = useState(null);
  const [sizeError, setSizeError] = useState("");
  const [pending, setPending] = useState(false);
  const [risk, setRisk] = useState("");
  const [targetMode, setTargetMode] = useState("price");
  const [targetR, setTargetR] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [suggestMessage, setSuggestMessage] = useState("");
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const chosenSymbol = useRef("");
  const previewSeq = useRef(0);
  const account = accountForVenue(form.venue, deltaAccounts, mt5Accounts);
  const orderTarget = targetMode === "r"
    ? targetPriceFromR(form.side, form.entry, form.stopLoss, targetR)
    : roundToStep(form.target);
  const liveRr = targetMode === "r"
    ? (Number(targetR) > 0 ? Number(targetR) : null)
    : rewardRisk(form.side, form.entry, form.stopLoss, orderTarget);
  const checkedTarget = targetMode === "r"
    ? (targetR === "" || targetR == null ? null : (orderTarget ?? targetR))
    : (form.target === "" ? null : (orderTarget ?? form.target));
  const priceError = orderPriceMessage(form.side, form.entry, form.stopLoss, checkedTarget);
  const stopDistance = Math.abs(Number(form.entry) - Number(form.stopLoss));
  const livePrice = livePriceFromTick(lookupLiveTick(livePrices, form.symbol));

  useEffect(() => {
    setRisk(account?.riskAmount ?? "");
    setTargetMode(account?.targetMode === "r" ? "r" : "price");
    setTargetR(account?.targetR ?? "");
  }, [account?.id, account?.riskAmount, account?.targetMode, account?.targetR, form.venue]);

  useEffect(() => {
    const text = form.symbol.trim();
    if (text.length < 2 || text.toUpperCase() === chosenSymbol.current) {
      setSuggestions([]);
      setSuggestMessage("");
      setSuggestOpen(false);
      return undefined;
    }
    let cancelled = false;
    const handle = window.setTimeout(() => {
      const params = new URLSearchParams({ venue: form.venue, q: text, includeOwned: "true" });
      api(`/watchlist/suggest?${params}`, { token })
        .then((data) => {
          if (cancelled) return;
          const rows = data.suggestions || [];
          setSuggestions(rows);
          setSuggestMessage(data.message || (rows.length ? "" : "No matches"));
          setSuggestOpen(true);
          setHighlight(0);
        })
        .catch((err) => {
          if (cancelled) return;
          setSuggestions([]);
          setSuggestMessage(err.message || "Suggestions are unavailable.");
          setSuggestOpen(true);
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [form.symbol, form.venue, token]);

  const set = (key) => (event) => {
    setPreview(null);
    setSizeError("");
    if (key === "symbol") chosenSymbol.current = "";
    setForm((current) => ({ ...current, [key]: event.target.value }));
  };

  const chooseSymbol = (symbol) => {
    const next = String(symbol || "").toUpperCase();
    const venue = form.venue;
    chosenSymbol.current = next;
    setSuggestOpen(false);
    setSuggestions([]);
    setPreview(null);
    setForm((current) => ({ ...current, symbol: next }));
    api("/market/subscribe", { method: "POST", token, body: { venue, symbol: next } })
      .catch((err) => onNotify("error", err.message || "Live price is unavailable."));
  };

  const onSymbolKeyDown = (event) => {
    if (!suggestOpen || suggestions.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlight((index) => (index + 1) % suggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlight((index) => (index - 1 + suggestions.length) % suggestions.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      chooseSymbol(suggestions[highlight]?.symbol);
    } else if (event.key === "Escape") {
      setSuggestOpen(false);
    }
  };

  const body = {
    venue: form.venue,
    symbol: form.symbol.trim().toUpperCase(),
    side: form.side,
    orderType: form.orderType,
    entry: form.entry === "" ? null : Number(form.entry),
    stopLoss: form.stopLoss === "" ? null : Number(form.stopLoss),
    target: orderTarget,
  };

  const ensureSelected = async () => {
    if (!account || account.selected) return;
    const path = form.venue === "forex" ? "/mt5/accounts/select" : "/accounts/select";
    await api(path, { method: "POST", token, body: { accountId: account.id } });
    onReload?.();
  };

  const saveRisk = async () => {
    if (!account) return;
    const next = Number(risk);
    if (!Number.isFinite(next) || next <= 0) {
      onNotify("error", "Risk amount must be greater than 0.");
      setRisk(account.riskAmount ?? "");
      return;
    }
    if (next === Number(account.riskAmount)) return;
    const path = form.venue === "forex" ? `/mt5/accounts/${account.id}/risk` : `/accounts/${account.id}/risk`;
    await api(path, { method: "PATCH", token, body: { riskAmount: next } });
    onNotify("success", "Risk amount saved.");
    onReload?.();
  };

  const saveTarget = async (mode, multiple) => {
    if (!account) return;
    const next = multiple === "" || multiple == null ? null : Number(multiple);
    if (next != null && (!Number.isFinite(next) || next <= 0)) {
      onNotify("error", "R multiple must be greater than 0.");
      setTargetR(account.targetR ?? "");
      return;
    }
    const path = form.venue === "forex" ? `/mt5/accounts/${account.id}/target` : `/accounts/${account.id}/target`;
    await api(path, { method: "PATCH", token, body: { targetMode: mode, targetR: next } });
    onReload?.();
  };

  const runPreview = async ({ quiet = false } = {}) => {
    if (priceError) {
      setPreview(null);
      if (!quiet) onNotify("error", priceError);
      return;
    }
    const seq = previewSeq.current + 1;
    previewSeq.current = seq;
    if (!quiet) setPending(true);
    try {
      await ensureSelected();
      const result = await api("/orders/preview", { method: "POST", token, body });
      if (seq !== previewSeq.current) return;
      setPreview(result);
      setSizeError("");
    } catch (err) {
      if (seq !== previewSeq.current) return;
      setPreview(null);
      const message = err.message || "Could not size this order.";
      setSizeError(message);
      if (!quiet) onNotify("error", message);
    } finally {
      if (!quiet && seq === previewSeq.current) setPending(false);
    }
  };

  useEffect(() => {
    const entry = Number(form.entry);
    const stop = Number(form.stopLoss);
    const symbol = form.symbol.trim();
    if (priceError || symbol.length < 2 || !(entry > 0) || !(stop > 0) || entry === stop || !(Number(risk) > 0)) {
      return undefined;
    }
    const handle = window.setTimeout(() => {
      runPreview({ quiet: true });
    }, 400);
    return () => {
      previewSeq.current += 1;
      window.clearTimeout(handle);
    };
  }, [form.symbol, form.entry, form.stopLoss, form.side, form.venue, form.target, targetMode, targetR, risk, account?.id, priceError]);

  const place = async () => {
    if (priceError) {
      onNotify("error", priceError);
      return;
    }
    setPending(true);
    try {
      await ensureSelected();
      await api("/orders", { method: "POST", token, body });
      onNotify("success", "Order sent.");
      setPreview(null);
    } catch (err) {
      onNotify("error", err.message || "Order was not sent.");
    } finally {
      setPending(false);
    }
  };

  const summary = [
    ["Account", account?.accountName || "—"],
    ["Venue", form.venue],
    ["Risk", Number(risk) > 0 ? money(risk) : "—"],
    ["Quantity", preview?.quantity ?? (sizeError || "—")],
    ["R:R", liveRr == null ? "—" : `1:${Number(liveRr).toFixed(targetMode === "r" ? 2 : 1)}`],
    ["Stop distance", Number.isFinite(stopDistance) && stopDistance > 0 ? stopDistance : "—"],
  ];

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className={`p-6 ${ledgerPanel}`}>
        <h1 className="text-xl">Trade</h1>
        <p className={`mt-1 text-sm ${ledgerMuted}`}>Size comes from the risk amount for this venue.</p>
        <div className="mt-5 grid gap-3">
          <ChoiceSwitch
            label="Venue"
            value={form.venue}
            onChange={(venue) => {
              setForm((current) => ({ ...current, venue }));
              setPreview(null);
              const next = accountForVenue(venue, deltaAccounts, mt5Accounts);
              if (next && !next.selected) {
                const path = venue === "forex" ? "/mt5/accounts/select" : "/accounts/select";
                api(path, { method: "POST", token, body: { accountId: next.id } })
                  .then(() => onReload?.())
                  .catch((err) => onNotify("error", err.message || "Could not select that account."));
              }
            }}
            options={[["crypto", "Crypto"], ["forex", "Forex"]]}
          />
          <label className="text-sm">
            <span className="inline-flex items-center gap-1.5">
              <ShieldAlert size={14} />
              Risk amount (USD)
            </span>
            {account ? (
              <input
                className={`mt-1 ${ledgerField}`}
                value={risk}
                onChange={(event) => setRisk(event.target.value)}
                onBlur={() => saveRisk().catch((err) => onNotify("error", err.message || "Could not save the risk amount."))}
              />
            ) : (
              <p className={`mt-1 text-sm ${ledgerMuted}`}>Select a {form.venue} account in Settings.</p>
            )}
            {account ? <span className={`mt-1 block text-xs ${ledgerMuted}`}>{account.accountName}</span> : null}
          </label>
          <label className={`text-sm ${suggestOpen ? "relative z-30" : "relative"}`}>
            Symbol
            <input
              className={`mt-1 ${ledgerField}`}
              value={form.symbol}
              onChange={set("symbol")}
              onKeyDown={onSymbolKeyDown}
              onFocus={() => {
                if (suggestions.length) setSuggestOpen(true);
              }}
            />
            {livePrice != null ? (
              <PriceFlashTicker value={livePrice} className={`mt-1 text-xs ${ledgerMuted}`}>
                {formatPrice(livePrice)}
              </PriceFlashTicker>
            ) : null}
            {suggestOpen && (suggestions.length || suggestMessage) ? (
              <div className={`absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-xl shadow-xl ${ledgerPanel}`}>
                {suggestMessage ? <p className={`px-3 py-2 text-xs ${ledgerMuted}`}>{suggestMessage}</p> : null}
                {suggestions.map((item, index) => (
                  <button
                    key={`${item.venue}:${item.symbol}`}
                    type="button"
                    className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm ${index === highlight ? "bg-[var(--ledger-accent)]/15" : ""}`}
                    onMouseDown={(event) => event.preventDefault()}
                    onMouseEnter={() => setHighlight(index)}
                    onClick={() => chooseSymbol(item.symbol)}
                  >
                    <span>{item.symbol}</span>
                    <span className="text-[11px] uppercase tracking-wider text-[var(--ledger-accent)]">{item.venue}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </label>
          <ChoiceSwitch
            label="Side"
            tone="side"
            value={form.side}
            onChange={(side) => setForm((current) => ({ ...current, side }))}
            options={[["BUY", "Buy"], ["SELL", "Sell"]]}
          />
          <div>
            <p className="mb-1 inline-flex items-center gap-1.5 text-sm">
              <SlidersHorizontal size={14} />
              Order
            </p>
          <ChoiceSwitch
            value={form.orderType}
            onChange={(orderType) => setForm((current) => ({ ...current, orderType }))}
            options={[["LIMIT", "Limit"], ["MARKET", "Market"], ["SL", "Stop"]]}
          />
          </div>
          <div className="grid grid-cols-3 gap-3">
            {["entry", "stopLoss"].map((key) => (
              <label key={key} className="text-sm capitalize">
                {key === "stopLoss" ? "Stop" : key}
                <input className={`mt-1 ${ledgerField}`} value={form[key]} onChange={set(key)} />
              </label>
            ))}
            <div className="text-sm">
              <ChoiceSwitch
                value={targetMode}
                onChange={(mode) => {
                  setTargetMode(mode);
                  saveTarget(mode, targetR).catch((err) => onNotify("error", err.message || "Could not save the target choice."));
                }}
                options={[["price", "Price"], ["r", "R"]]}
              />
              {targetMode === "r" ? (
                <>
                  <input
                    className={`mt-1 ${ledgerField}`}
                    inputMode="decimal"
                    placeholder="R multiple"
                    value={targetR}
                    onChange={(event) => setTargetR(limitR(event.target.value))}
                    onBlur={() => saveTarget("r", targetR).catch((err) => onNotify("error", err.message || "Could not save the R multiple."))}
                  />
                  <span className={`mt-1 block text-xs ${ledgerMuted}`}>
                    {orderTarget == null ? "Target price appears after entry and stop" : `Target ${formatPrice(orderTarget)}`}
                  </span>
                </>
              ) : (
                <input className={`mt-1 ${ledgerField}`} placeholder="Target price" value={form.target} onChange={set("target")} />
              )}
            </div>
          </div>
          {priceError ? <p className="text-sm text-[var(--ledger-loss)]">{priceError}</p> : null}
        </div>
        <div className={`mt-4 p-3 text-sm ${ledgerPanel}`}>
          <p className={ledgerMuted}>Reward to risk</p>
          <p className="mt-1 text-2xl font-semibold">{liveRr == null ? "—" : `1:${Number(liveRr).toFixed(targetMode === "r" ? 2 : 1)}`}</p>
          <p className={`mt-1 ${ledgerMuted}`}>Quantity {preview?.quantity ?? (sizeError || "fills in after entry and stop")}</p>
        </div>
        <div className="mt-5 flex gap-2">
          <button type="button" disabled={pending || Boolean(priceError)} onClick={() => runPreview()} className="rounded-full border border-[var(--ledger-accent)] px-4 py-2 text-sm text-[var(--ledger-accent)]">
            Preview
          </button>
          <button
            type="button"
            disabled={pending || !preview || Boolean(priceError)}
            onClick={place}
            className="rounded-full bg-[var(--ledger-accent)] px-4 py-2 text-sm text-white transition hover:brightness-110 disabled:opacity-50"
          >
            Place Order
          </button>
        </div>
      </section>
      <section className={`flex min-h-[28rem] flex-col p-6 ${ledgerPanel}`}>
        <h2 className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--ledger-muted)]">Risk summary</h2>
        <p className="mt-2 text-2xl font-bold">{form.symbol.trim().toUpperCase() || "Symbol"}</p>
        <dl className="mt-6 grid flex-1 content-start">
          {summary.map(([label, value]) => (
            <div key={label} className="border-b border-[var(--ledger-border)] py-3">
              <div className="flex items-center justify-between text-sm">
                <dt className={`text-xs uppercase tracking-[0.12em] ${ledgerMuted}`}>{label}</dt>
                <dd className="font-semibold capitalize">{value}</dd>
              </div>
              {label === "R:R" ? <RewardRiskBar ratio={liveRr} /> : null}
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
