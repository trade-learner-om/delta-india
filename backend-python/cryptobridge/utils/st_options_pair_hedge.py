"""Pure helpers for ST Options backtest same-strike opposite pair hedge."""

from __future__ import annotations

from typing import Literal

from cryptobridge.utils.st_options_resolver import OptionSide
from cryptobridge.utils.st_options_strategy import premium_decay_pct

PairHedgeMode = Literal["immediate", "on_decay"]

VALID_PAIR_HEDGE_MODES = frozenset({"immediate", "on_decay"})
DEFAULT_PAIR_HEDGE_MODE: PairHedgeMode = "immediate"
DEFAULT_PAIR_HEDGE_DECAY_PCT = 40.0


def opposite_option_side(side: OptionSide | str) -> OptionSide:
    s = str(side or "").upper()
    return "CALL" if s == "PUT" else "PUT"


def pair_premiums_equal(put_prem: float, call_prem: float) -> bool:
    """True when |put − call| ≤ max(1, 0.02 × avg)."""
    put = float(put_prem)
    call = float(call_prem)
    if put < 0 or call < 0:
        return False
    avg = (put + call) / 2.0
    tol = max(1.0, 0.02 * avg)
    return abs(put - call) <= tol


def should_open_decay_hedge(
    entry_premium: float,
    live_premium: float,
    decay_pct: float,
) -> bool:
    """True when main premium has melted by at least decay_pct."""
    pct = float(decay_pct)
    if pct <= 0:
        return True
    return premium_decay_pct(entry_premium, live_premium) >= pct


def hedge_stop_premium(
    hedge_entry: float,
    main_profit_usd: float,
    max_risk: float,
    contract_value: float,
    lots: int,
) -> float | None:
    """Fixed hedge SL premium frozen at hedge open.

    hedgeStop = hedgeEntry + (mainProfit$ + maxRisk) / (cv × lots)

    Returns None when notional is invalid or remaining budget ≤ 0.
    """
    entry = float(hedge_entry)
    notional = float(contract_value) * int(lots)
    if entry <= 0 or notional <= 0:
        return None
    budget = float(main_profit_usd) + float(max_risk)
    if budget <= 0:
        return None
    return entry + budget / notional


def normalize_pair_hedge_mode(raw: str | None) -> PairHedgeMode:
    mode = str(raw or DEFAULT_PAIR_HEDGE_MODE).strip().lower()
    if mode not in VALID_PAIR_HEDGE_MODES:
        return DEFAULT_PAIR_HEDGE_MODE
    return mode  # type: ignore[return-value]
