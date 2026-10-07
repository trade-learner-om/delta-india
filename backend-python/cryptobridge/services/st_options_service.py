"""ST Options service — config, live engine, history, async backtest jobs."""

from __future__ import annotations

import asyncio
import base64
import bisect
import contextlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from cryptobridge.config import settings
from cryptobridge.delta.market_data import DeltaMarketDataService
from cryptobridge.delta.rest_client import (
    CandleBar,
    DeltaRestClient,
    OrderSummary,
    ProductSummary,
    normalize_order_size,
    normalize_symbol,
)
from cryptobridge.delta.request_signing import parse_delta_error_body
from cryptobridge.exceptions import http_error
from cryptobridge.services.account_service import AccountService
from cryptobridge.utils import crypto as secret_crypto
from cryptobridge.utils.positions_helpers import is_open_order_status
from cryptobridge.utils.st_options_backtest import (
    BacktestResult,
    DynamicSizingConfig,
    DynamicSizingState,
    LIVE_SL_SLIPPAGE_BUFFER_PCT,
    LIVE_STRIKE_DEPTH,
    OpenTrade,
    _close_hedge_leg,
    _close_trade,
    _manage_open,
    arm_skip_after_take_profit,
    clear_formation_block,
    compute_summary,
    consume_skip_setup,
    entry_limit_price,
    formation_blocks_entry,
    lots_from_max_risk_or_none,
    result_to_dict,
)
from cryptobridge.utils.st_options_indicators import IndicatorBar, OhlcBar, compute_indicator_bars
from cryptobridge.utils.st_options_pair_hedge import (
    hedge_stop_premium,
    normalize_pair_hedge_mode,
    opposite_option_side,
    should_open_decay_hedge,
)
from cryptobridge.utils.st_options_resolver import (
    Direction,
    FORCE_CLOSE_IST,
    bar_close_unix,
    collect_option_waterfall,
    contract_value_for,
    delta_option_symbol,
    eligible_expiries,
    expiry_dates_t0_t1,
    format_ist,
    normalize_underlying,
    option_side_for_direction,
    parse_option_symbol_expiry,
    parse_strike_type,
    perp_symbol,
    pick_above_average_volume,
    product_matches_expiry,
    resolve_backtest_strike,
    settlement_intrinsic,
    settlement_unix,
    strike_band_min_max,
    strike_in_band,
    strike_ladder,
)
from cryptobridge.utils.st_options_strategy import (
    DEFAULT_BREAKEVEN_DECAY_PCT,
    DEFAULT_EMA_LENGTH,
    DEFAULT_MAX_ST_DISTANCE_PCT,
    DEFAULT_MIN_PREMIUM_PCT,
    DEFAULT_ST_MULTIPLIER,
    DEFAULT_ST_PERIOD,
    DEFAULT_STOP_LOSS_PCT,
    DEFAULT_TAKE_PROFIT_PCT,
    RESOLUTION,
    RESOLUTION_SECONDS,
    WARMUP_DAYS,
    build_entry_signal,
    entry_ready,
    evaluate_premium_brackets,
    opposite_st_exit,
    should_move_sl_to_breakeven,
    short_option_pnl,
    st_distance_within,
    stop_premium,
    target_premium,
)

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

CONFIG_COLLECTION = "st_options_config"
TRADES_COLLECTION = "st_options_trades"
BACKTEST_CONFIG_COLLECTION = "st_options_backtest_config"
BACKTEST_RUNS_COLLECTION = "st_options_backtest_runs"
BACKTEST_RUNS_KEEP = 50
BACKTEST_FETCH_CONCURRENCY = 14
STATUS_OPEN = "open"
STATUS_CLOSED = "closed"
STATUS_PENDING_ENTRY = "pending_entry"
HISTORY_DEFAULT_LIMIT = 20
HISTORY_MAX_LIMIT = 100
POLL_SECONDS = 15.0
_BRACKET_FILL_STATUSES = frozenset({"CLOSED", "FILLED"})
_BRACKET_CANCEL_STATUSES = frozenset({"CANCELLED", "CANCELED", "REJECTED", "EXPIRED"})
_ACTIVE_TRADE_STATUSES = frozenset({STATUS_OPEN, STATUS_PENDING_ENTRY})

DEFAULT_DYN_AFTER_LOSSES = 2
DEFAULT_DYN_INCREASE_PCT = 10.0
DEFAULT_DYN_MAX_RISK_PCT = 200.0
DEFAULT_DYN_AFTER_PROFITS = 2
DEFAULT_DYN_DECREASE_PCT = 10.0
DEFAULT_MAX_RISK = 100.0
DEFAULT_STRIKE_SELECT_MODE = "min_pct"
DEFAULT_STRIKE_TYPE = "ATM"
DEFAULT_MIN_PREMIUM_ABS = 50.0
DEFAULT_SKIP_SETUPS_AFTER_TARGET = 1
DEFAULT_PAIR_HEDGE_DECAY_PCT = 40.0
DEFAULT_LIVE_PAIR_HEDGE_DECAY_PCT = 0.0  # 0 = hedging off on live
VALID_STRIKE_SELECT_MODES = frozenset({"fixed", "min_pct", "supertrend", "min_abs"})
VALID_PAIR_HEDGE_MODES = frozenset({"immediate", "on_decay"})
HEDGE_STATUS_NONE = "none"
HEDGE_STATUS_PENDING = "pending"
HEDGE_STATUS_OPEN = "open"
HEDGE_STATUS_CLOSED = "closed"


@dataclass
class BracketCancelResult:
    """Outcome of cancelling pending broker SL/TP before an intentional exit."""

    ok: bool
    filled_reason: str | None = None
    filled_order: Any | None = None
    cleared: bool = False


def _order_status(order: Any | None) -> str:
    return str(getattr(order, "status", "") or "").upper()


def _is_bracket_fill(order: Any | None) -> bool:
    return order is not None and _order_status(order) in _BRACKET_FILL_STATUSES


def _is_bracket_cancelled(order: Any | None) -> bool:
    return order is not None and _order_status(order) in _BRACKET_CANCEL_STATUSES


def _is_bracket_pending(order: Any | None) -> bool:
    if order is None:
        return True
    status = _order_status(order)
    return is_open_order_status(status) or status in {"", "PENDING"}


def _order_filled_size(order: Any | None) -> float:
    """Lots filled on a Delta order (supports full + partial fills)."""
    if order is None:
        return 0.0
    size = float(getattr(order, "size", None) or 0)
    unfilled = getattr(order, "unfilled_size", None)
    avg = getattr(order, "average_fill_price", None)
    try:
        avg_f = float(avg) if avg is not None else None
    except (TypeError, ValueError):
        avg_f = None
    if unfilled is not None:
        filled = size - float(unfilled)
        if filled > 1e-9:
            return filled
        # Delta sometimes leaves unfilled==size after a fill but still sets average_fill_price.
        if avg_f is not None and avg_f > 0 and size > 0:
            return size
    status = _order_status(order)
    if status in _BRACKET_FILL_STATUSES and size > 0:
        return size
    if status in _BRACKET_FILL_STATUSES and avg_f is not None and avg_f > 0:
        return size if size > 0 else 1.0
    if avg_f is not None and avg_f > 0 and size > 0:
        return size
    return 0.0


def _is_limit_entry_filled(order: Any | None) -> bool:
    """True when any size filled — average_fill_price alone also counts (Delta may mis-state status)."""
    if order is None:
        return False
    if _order_filled_size(order) > 0:
        return True
    if _order_status(order) in _BRACKET_FILL_STATUSES:
        return True
    avg = getattr(order, "average_fill_price", None)
    try:
        return avg is not None and float(avg) > 0
    except (TypeError, ValueError):
        return False


def _order_fill_debug(order: Any | None) -> str:
    if order is None:
        return "order=None"
    return (
        f"status={_order_status(order)} size={getattr(order, 'size', None)} "
        f"unfilled={getattr(order, 'unfilled_size', None)} "
        f"avgFill={getattr(order, 'average_fill_price', None)} id={getattr(order, 'id', None)}"
    )


def _cancel_looks_like_gone(exc: BaseException) -> bool:
    """True when cancel failed because the order is already terminal (filled/cancelled)."""
    text = str(getattr(exc, "detail", None) or exc).lower()
    return (
        "404" in text
        or "not found" in text
        or "order_not_found" in text
        or "already" in text and ("fill" in text or "cancel" in text or "closed" in text)
    )


PENDING_UNFILLED_CONFIRM_TICKS = 3
PENDING_MIN_AGE_SECONDS = 150
POSITION_RECOVERY_ATTEMPTS = 8
ENTRY_CANCEL_RETRIES = 3


def _short_position_lots_and_entry(raw: dict[str, Any]) -> tuple[float, float | None] | None:
    """Parse a Delta margined position row; return (lots, entry) for shorts only."""
    size = float(raw.get("size") or 0)
    if size >= 0:
        return None
    entry = raw.get("entry_price") or raw.get("average_entry_price") or raw.get("avg_entry_price")
    try:
        entry_f = float(entry) if entry is not None else None
    except (TypeError, ValueError):
        entry_f = None
    if entry_f is not None and entry_f <= 0:
        entry_f = None
    return abs(size), entry_f


def _extract_delta_error_payload(exc: BaseException) -> dict[str, Any]:
    """Best-effort parse of Delta error dict from an HTTPException / wrapped body."""
    detail = getattr(exc, "detail", None)
    candidates: list[str] = []
    if isinstance(detail, dict):
        for key in ("error", "detail", "message"):
            val = detail.get(key)
            if val is not None:
                candidates.append(str(val))
        with contextlib.suppress(TypeError, ValueError):
            candidates.append(json.dumps(detail))
    elif detail is not None:
        candidates.append(str(detail))
    candidates.append(str(exc))
    for text in candidates:
        parsed = parse_delta_error_body(text)
        if parsed.get("code"):
            return parsed
        match = re.search(r"(\{(?:[^{}]|\{[^{}]*\})*\})", text)
        if match:
            nested = parse_delta_error_body(match.group(1))
            if nested.get("code"):
                return nested
            # Body may wrap another JSON string after "Delta API request failed: "
            inner = re.search(r"Delta API request failed:\s*(\{.*\})", text)
            if inner:
                nested = parse_delta_error_body(inner.group(1))
                if nested.get("code"):
                    return nested
    return {}


def _order_failure_user_message(exc: BaseException, *, kind: str = "setup") -> str:
    """Plain Updates line for a failed place_order (insufficient margin, etc.)."""
    prefix = "Setup skipped" if kind == "setup" else "Hedge order failed"
    err = _extract_delta_error_payload(exc)
    code = str(err.get("code") or "").strip().lower()
    ctx = err.get("context") if isinstance(err.get("context"), dict) else {}
    if code == "insufficient_margin":
        parts: list[str] = []
        with contextlib.suppress(TypeError, ValueError):
            need = ctx.get("required_additional_balance")
            avail = ctx.get("available_balance")
            if need is not None:
                parts.append(f"need ~${float(need):.2f} more")
            if avail is not None:
                parts.append(f"available ~${float(avail):.2f}")
        extra = f" ({'; '.join(parts)})" if parts else ""
        if kind == "setup":
            return f"Setup skipped — insufficient margin{extra}"
        return f"Hedge order failed — insufficient margin{extra}"
    if code:
        label = code.replace("_", " ")
        if kind == "setup":
            return f"Setup skipped — {label}"
        return f"Hedge order failed — {label}"
    if kind == "setup":
        return "Setup skipped — order could not be placed"
    return prefix


class StOptionsBroadcaster:
    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

    def subscribe(self, user_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        self._queues.setdefault(user_id, set()).add(queue)
        return queue

    def unsubscribe(self, user_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        buckets = self._queues.get(user_id)
        if not buckets:
            return
        buckets.discard(queue)
        if not buckets:
            self._queues.pop(user_id, None)

    def publish(self, user_id: str, payload: dict[str, Any]) -> None:
        for queue in list(self._queues.get(user_id, set())):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(payload)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _default_config(user_id: str) -> dict[str, Any]:
    return {
        "userId": user_id,
        "enabled": False,
        "underlying": "BTC",
        "maxRisk": DEFAULT_MAX_RISK,
        "stPeriod": DEFAULT_ST_PERIOD,
        "stMultiplier": DEFAULT_ST_MULTIPLIER,
        "emaLength": DEFAULT_EMA_LENGTH,
        "minPremiumPct": DEFAULT_MIN_PREMIUM_PCT,
        "stopLossPct": DEFAULT_STOP_LOSS_PCT,
        "takeProfitPct": DEFAULT_TAKE_PROFIT_PCT,
        "breakevenDecayPct": DEFAULT_BREAKEVEN_DECAY_PCT,
        "pairHedgeDecayPct": DEFAULT_LIVE_PAIR_HEDGE_DECAY_PCT,
        "maxStDistancePct": DEFAULT_MAX_ST_DISTANCE_PCT,
        "updatedAt": _now(),
    }


def _default_backtest_config(user_id: str) -> dict[str, Any]:
    return {
        "userId": user_id,
        "underlying": "BTC",
        "maxRisk": DEFAULT_MAX_RISK,
        "stPeriod": DEFAULT_ST_PERIOD,
        "stMultiplier": DEFAULT_ST_MULTIPLIER,
        "emaLength": DEFAULT_EMA_LENGTH,
        "minPremiumPct": DEFAULT_MIN_PREMIUM_PCT,
        "stopLossPct": DEFAULT_STOP_LOSS_PCT,
        "takeProfitPct": DEFAULT_TAKE_PROFIT_PCT,
        "breakevenDecayPct": DEFAULT_BREAKEVEN_DECAY_PCT,
        "dynamicSizingEnabled": False,
        "dynAfterLosses": DEFAULT_DYN_AFTER_LOSSES,
        "dynIncreasePct": DEFAULT_DYN_INCREASE_PCT,
        "dynMaxRiskPct": DEFAULT_DYN_MAX_RISK_PCT,
        "dynAfterProfits": DEFAULT_DYN_AFTER_PROFITS,
        "dynDecreasePct": DEFAULT_DYN_DECREASE_PCT,
        "strikeSelectMode": DEFAULT_STRIKE_SELECT_MODE,
        "strikeType": DEFAULT_STRIKE_TYPE,
        "minPremiumAbs": DEFAULT_MIN_PREMIUM_ABS,
        "oneTradePerFormation": False,
        "skipSetupsAfterTarget": DEFAULT_SKIP_SETUPS_AFTER_TARGET,
        "maxStDistancePct": DEFAULT_MAX_ST_DISTANCE_PCT,
        "pairHedgeEnabled": False,
        "pairHedgeMode": "immediate",
        "pairHedgeDecayPct": DEFAULT_PAIR_HEDGE_DECAY_PCT,
        "updatedAt": _now(),
    }


def _apply_breakeven_decay_patch(updates: dict[str, Any], patch: dict[str, Any]) -> None:
    if patch.get("breakevenDecayPct") is None:
        return
    pct = float(patch["breakevenDecayPct"])
    if pct < 0 or pct >= 100:
        raise http_error(400, "breakevenDecayPct must be >= 0 and < 100 (0 = off)")
    updates["breakevenDecayPct"] = pct


def _apply_pair_hedge_decay_patch(updates: dict[str, Any], patch: dict[str, Any]) -> None:
    if patch.get("pairHedgeDecayPct") is None:
        return
    pct = float(patch["pairHedgeDecayPct"])
    if pct < 0 or pct >= 100:
        raise http_error(400, "pairHedgeDecayPct must be >= 0 and < 100 (0 = off)")
    updates["pairHedgeDecayPct"] = pct


def _apply_max_st_distance_patch(updates: dict[str, Any], patch: dict[str, Any]) -> None:
    if patch.get("maxStDistancePct") is None:
        return
    dist = float(patch["maxStDistancePct"])
    if dist < 0:
        raise http_error(400, "maxStDistancePct must be >= 0 (0 = off)")
    updates["maxStDistancePct"] = dist


def _ticker_premium(ticker: Any) -> float | None:
    if ticker is None:
        return None
    premium = getattr(ticker, "mark_price", None) or getattr(ticker, "last_price", None)
    if premium is None:
        bid = getattr(ticker, "bid", None)
        ask = getattr(ticker, "ask", None)
        if bid is not None and ask is not None:
            premium = (float(bid) + float(ask)) / 2.0
    return float(premium) if premium is not None else None


def _hedge_is_open(doc: dict[str, Any]) -> bool:
    return (
        str(doc.get("hedgeStatus") or "") == HEDGE_STATUS_OPEN
        and doc.get("hedgeSymbol")
        and doc.get("hedgePremiumReceived") is not None
    )


def _iso_utc(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return str(value)


def config_to_view(doc: dict[str, Any]) -> dict[str, Any]:
    # Prefer maxRisk; fall back for older docs that only stored quantity.
    max_risk = doc.get("maxRisk")
    if max_risk is None and doc.get("quantity") is not None:
        max_risk = DEFAULT_MAX_RISK
    return {
        "enabled": bool(doc.get("enabled")),
        "underlying": doc.get("underlying", "BTC"),
        "maxRisk": float(max_risk if max_risk is not None else DEFAULT_MAX_RISK),
        "stPeriod": int(doc.get("stPeriod", DEFAULT_ST_PERIOD)),
        "stMultiplier": float(doc.get("stMultiplier", DEFAULT_ST_MULTIPLIER)),
        "emaLength": int(doc.get("emaLength", DEFAULT_EMA_LENGTH)),
        "minPremiumPct": float(doc.get("minPremiumPct", DEFAULT_MIN_PREMIUM_PCT)),
        "stopLossPct": float(doc.get("stopLossPct", DEFAULT_STOP_LOSS_PCT)),
        "takeProfitPct": float(doc.get("takeProfitPct", DEFAULT_TAKE_PROFIT_PCT)),
        "breakevenDecayPct": float(doc.get("breakevenDecayPct", DEFAULT_BREAKEVEN_DECAY_PCT)),
        "pairHedgeDecayPct": float(
            doc.get("pairHedgeDecayPct", DEFAULT_LIVE_PAIR_HEDGE_DECAY_PCT)
            if doc.get("pairHedgeDecayPct") is not None
            else DEFAULT_LIVE_PAIR_HEDGE_DECAY_PCT
        ),
        "maxStDistancePct": float(
            doc.get("maxStDistancePct", DEFAULT_MAX_ST_DISTANCE_PCT)
            if doc.get("maxStDistancePct") is not None
            else DEFAULT_MAX_ST_DISTANCE_PCT
        ),
        "updatedAt": _iso_utc(doc.get("updatedAt")),
    }


def backtest_config_to_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "underlying": doc.get("underlying", "BTC"),
        "maxRisk": float(doc.get("maxRisk", DEFAULT_MAX_RISK)),
        "stPeriod": int(doc.get("stPeriod", DEFAULT_ST_PERIOD)),
        "stMultiplier": float(doc.get("stMultiplier", DEFAULT_ST_MULTIPLIER)),
        "emaLength": int(doc.get("emaLength", DEFAULT_EMA_LENGTH)),
        "minPremiumPct": float(doc.get("minPremiumPct", DEFAULT_MIN_PREMIUM_PCT)),
        "stopLossPct": float(doc.get("stopLossPct", DEFAULT_STOP_LOSS_PCT)),
        "takeProfitPct": float(doc.get("takeProfitPct", DEFAULT_TAKE_PROFIT_PCT)),
        "breakevenDecayPct": float(doc.get("breakevenDecayPct", DEFAULT_BREAKEVEN_DECAY_PCT)),
        "dynamicSizingEnabled": bool(doc.get("dynamicSizingEnabled", False)),
        "dynAfterLosses": int(doc.get("dynAfterLosses", DEFAULT_DYN_AFTER_LOSSES)),
        "dynIncreasePct": float(doc.get("dynIncreasePct", DEFAULT_DYN_INCREASE_PCT)),
        "dynMaxRiskPct": float(doc.get("dynMaxRiskPct", DEFAULT_DYN_MAX_RISK_PCT)),
        "dynAfterProfits": int(doc.get("dynAfterProfits", DEFAULT_DYN_AFTER_PROFITS)),
        "dynDecreasePct": float(doc.get("dynDecreasePct", DEFAULT_DYN_DECREASE_PCT)),
        "strikeSelectMode": str(doc.get("strikeSelectMode") or DEFAULT_STRIKE_SELECT_MODE),
        "strikeType": str(doc.get("strikeType") or DEFAULT_STRIKE_TYPE),
        "minPremiumAbs": float(doc.get("minPremiumAbs", DEFAULT_MIN_PREMIUM_ABS)),
        "oneTradePerFormation": bool(doc.get("oneTradePerFormation", False)),
        "skipSetupsAfterTarget": int(
            doc.get("skipSetupsAfterTarget", DEFAULT_SKIP_SETUPS_AFTER_TARGET)
            if doc.get("skipSetupsAfterTarget") is not None
            else DEFAULT_SKIP_SETUPS_AFTER_TARGET
        ),
        "maxStDistancePct": float(
            doc.get("maxStDistancePct", DEFAULT_MAX_ST_DISTANCE_PCT)
            if doc.get("maxStDistancePct") is not None
            else DEFAULT_MAX_ST_DISTANCE_PCT
        ),
        "pairHedgeEnabled": bool(doc.get("pairHedgeEnabled", False)),
        "pairHedgeMode": str(doc.get("pairHedgeMode") or "immediate"),
        "pairHedgeDecayPct": float(
            doc.get("pairHedgeDecayPct", DEFAULT_PAIR_HEDGE_DECAY_PCT)
            if doc.get("pairHedgeDecayPct") is not None
            else DEFAULT_PAIR_HEDGE_DECAY_PCT
        ),
        "updatedAt": _iso_utc(doc.get("updatedAt")),
    }


def _dynamic_sizing_from_body(body: dict[str, Any] | None) -> DynamicSizingConfig:
    body = body or {}
    return DynamicSizingConfig(
        enabled=bool(body.get("dynamicSizingEnabled", False)),
        after_losses=int(body.get("dynAfterLosses", DEFAULT_DYN_AFTER_LOSSES) or DEFAULT_DYN_AFTER_LOSSES),
        increase_pct=float(body.get("dynIncreasePct", DEFAULT_DYN_INCREASE_PCT) or DEFAULT_DYN_INCREASE_PCT),
        max_risk_pct=float(body.get("dynMaxRiskPct", DEFAULT_DYN_MAX_RISK_PCT) or DEFAULT_DYN_MAX_RISK_PCT),
        after_profits=int(body.get("dynAfterProfits", DEFAULT_DYN_AFTER_PROFITS) or DEFAULT_DYN_AFTER_PROFITS),
        decrease_pct=float(body.get("dynDecreasePct", DEFAULT_DYN_DECREASE_PCT) or DEFAULT_DYN_DECREASE_PCT),
    )


def _option_candle_window(
    symbol: str, window_start: int, candle_end: int
) -> tuple[int, int]:
    """Narrow option candle fetch to window ± buffer through settlement (not 120d warmup)."""
    start = max(0, int(window_start) - 3600)
    expiry = parse_option_symbol_expiry(symbol)
    if expiry is not None:
        end = min(int(candle_end), settlement_unix(expiry) + 3600)
    else:
        end = int(candle_end)
    if end <= start:
        end = start + 3600
    return start, end


def trade_to_view(doc: dict[str, Any]) -> dict[str, Any]:
    entry = doc.get("premiumReceived")
    live = doc.get("livePremium")
    lots = int(doc.get("lots") or 1)
    raw_cv = doc.get("contractValue")
    if raw_cv is not None and float(raw_cv) > 0:
        cv = float(raw_cv)
    else:
        cv = float(contract_value_for(doc.get("underlying") or "BTC"))
    main_pnl = None
    hedge_pnl = None
    pair_pnl = None
    est_at_stop = None
    est_at_target = None
    if entry is not None and str(doc.get("status")) in {STATUS_OPEN, STATUS_PENDING_ENTRY}:
        entry_f = float(entry)
        if live is not None:
            main_pnl = short_option_pnl(entry_f, float(live), cv, lots)
            if _hedge_is_open(doc):
                hedge_entry = float(doc["hedgePremiumReceived"])
                hedge_live = float(
                    doc["hedgeLivePremium"]
                    if doc.get("hedgeLivePremium") is not None
                    else hedge_entry
                )
                hedge_lots = int(doc.get("hedgeLots") or lots)
                hedge_pnl = short_option_pnl(hedge_entry, hedge_live, cv, hedge_lots)
                pair_pnl = main_pnl + hedge_pnl
            else:
                pair_pnl = main_pnl
        stop_px = doc.get("stopPremium")
        target_px = doc.get("targetPremium")
        if stop_px is not None:
            est_at_stop = short_option_pnl(entry_f, float(stop_px), cv, lots)
        if target_px is not None:
            est_at_target = short_option_pnl(entry_f, float(target_px), cv, lots)
    return {
        "id": str(doc.get("_id", "")),
        "direction": doc.get("direction"),
        "status": doc.get("status"),
        "underlying": doc.get("underlying"),
        "date": doc.get("date"),
        "stColour": doc.get("stColour"),
        "stColourChangeTime": doc.get("stColourChangeTime"),
        "emaPrice": doc.get("emaPrice"),
        "strike": doc.get("strike"),
        "expiryDate": doc.get("expiryDate"),
        "optionSymbol": doc.get("optionSymbol"),
        "optionSide": doc.get("optionSide"),
        "premiumReceived": doc.get("premiumReceived"),
        "exitPrice": doc.get("exitPrice"),
        "exitReason": doc.get("exitReason"),
        "pnl": doc.get("pnl"),
        "livePremium": doc.get("livePremium"),
        "stopPremium": doc.get("stopPremium"),
        "targetPremium": doc.get("targetPremium"),
        "stopLossPct": doc.get("stopLossPct"),
        "takeProfitPct": doc.get("takeProfitPct"),
        "breakevenDecayPct": doc.get("breakevenDecayPct"),
        "slMovedToBreakeven": bool(doc.get("slMovedToBreakeven")),
        "stopOrderId": doc.get("stopOrderId"),
        "takeProfitOrderId": doc.get("takeProfitOrderId"),
        "lots": lots,
        "contractValue": cv,
        "entryTime": doc.get("entryTime"),
        "exitTime": doc.get("exitTime"),
        "closeError": doc.get("closeError"),
        "pairId": doc.get("pairId"),
        "legRole": doc.get("legRole"),
        "hedgeStatus": doc.get("hedgeStatus") or HEDGE_STATUS_NONE,
        "hedgeSymbol": doc.get("hedgeSymbol"),
        "hedgePremiumReceived": doc.get("hedgePremiumReceived"),
        "hedgeLivePremium": doc.get("hedgeLivePremium"),
        "hedgeLots": doc.get("hedgeLots"),
        "hedgePending": bool(doc.get("hedgePending")),
        "hedgeStopPremium": doc.get("hedgeStopPremium"),
        "hedgeMainProfitAtOpen": doc.get("hedgeMainProfitAtOpen"),
        "hedgeStopOrderId": doc.get("hedgeStopOrderId"),
        "livePnl": main_pnl,
        "hedgeLivePnl": hedge_pnl,
        "pairLivePnl": pair_pnl,
        "estimatedPnlAtStop": est_at_stop,
        "estimatedPnlAtTarget": est_at_target,
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


def _product_side(product: ProductSummary) -> str:
    ctype = (product.contract_type or "").lower()
    if "put" in ctype or product.symbol.startswith("P-"):
        return "PUT"
    return "CALL"


def _encode_history_cursor(exit_time: Any, doc_id: Any) -> str:
    payload = json.dumps({"t": exit_time, "id": str(doc_id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_history_cursor(cursor: str) -> tuple[Any, ObjectId]:
    try:
        pad = "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(cursor + pad).decode("utf-8"))
        exit_time = data["t"]
        oid = ObjectId(str(data["id"]))
    except Exception as exc:
        raise http_error(400, "Invalid history cursor") from exc
    return exit_time, oid


def _empty_closed_summary() -> dict[str, Any]:
    return {
        "trades": 0,
        "long": 0,
        "short": 0,
        "profitCount": 0,
        "lossCount": 0,
        "maxProfit": 0.0,
        "maxLoss": 0.0,
        "totalProfit": 0.0,
        "totalLoss": 0.0,
        "totalPnl": 0.0,
        "lossToProfit": None,
    }


def _public_backtest_result(
    result: BacktestResult,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = result_to_dict(result)
    summary = raw["summary"]
    payload: dict[str, Any] = {
        "settings": raw["settings"],
        "summary": {
            "totalTrades": summary["total_trades"],
            "totalPnl": summary["total_pnl"],
            "longTrades": summary["long_trades"],
            "shortTrades": summary["short_trades"],
            "longPnl": summary["long_pnl"],
            "shortPnl": summary["short_pnl"],
            "maxProfit": summary["max_profit"],
            "maxProfitDate": summary["max_profit_date"],
            "maxLoss": summary["max_loss"],
            "maxLossDate": summary["max_loss_date"],
            "maxDrawdown": summary["max_drawdown"],
            "maxDdFrom": summary["max_dd_from"],
            "maxDdTo": summary["max_dd_to"],
            "winCount": summary.get("win_count", 0),
            "lossCount": summary.get("loss_count", 0),
            "maxWinStreakLen": summary.get("max_win_streak_len", 0),
            "maxWinStreakCount": summary.get("max_win_streak_count", 0),
            "maxLossStreakLen": summary.get("max_loss_streak_len", 0),
            "maxLossStreakCount": summary.get("max_loss_streak_count", 0),
            "avgProfit": summary.get("avg_profit"),
            "avgLoss": summary.get("avg_loss"),
        },
        "trades": [
            {
                "date": t["date"],
                "direction": t["direction"],
                "stColour": t["st_colour"],
                "stColourChangeTime": t["st_colour_change_time"],
                "emaPrice": t["ema_price"],
                "strike": t["strike"],
                "expiryDate": t["expiry_date"],
                "premiumReceived": t["premium_received"],
                "exitPrice": t["exit_price"],
                "exitReason": t["exit_reason"],
                "pnl": t["pnl"],
                "optionSymbol": t["option_symbol"],
                "entryTime": t["entry_time"],
                "exitTime": t["exit_time"],
                "lots": t.get("lots", 1),
                "pairId": t.get("pair_id"),
                "legRole": t.get("leg_role"),
            }
            for t in raw["trades"]
        ],
    }
    if diagnostics is not None:
        payload["diagnostics"] = diagnostics
    return payload


class StOptionsService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        delta: DeltaRestClient,
        account_service: AccountService,
        market: DeltaMarketDataService,
    ) -> None:
        self._db = db
        self._config = db[CONFIG_COLLECTION]
        self._trades = db[TRADES_COLLECTION]
        self._bt_config = db[BACKTEST_CONFIG_COLLECTION]
        self._bt_runs = db[BACKTEST_RUNS_COLLECTION]
        self._delta = delta
        self._accounts = account_service
        self._market = market
        self.broadcaster = StOptionsBroadcaster()
        self._task: asyncio.Task | None = None
        self._backtest_jobs: dict[str, dict[str, Any]] = {}
        self._last_processed_bar: dict[str, int] = {}
        self._last_tick_at: dict[str, datetime] = {}
        self._activity: dict[str, list[dict[str, Any]]] = {}

    async def ensure_indexes(self) -> None:
        await self._config.create_index("userId", unique=True)
        await self._trades.create_index([("userId", 1), ("status", 1), ("direction", 1)])
        await self._trades.create_index([("userId", 1), ("exitTime", -1)])
        await self._trades.create_index([("userId", 1), ("status", 1), ("exitTime", -1), ("_id", -1)])
        await self._bt_config.create_index("userId", unique=True)
        await self._bt_runs.create_index([("userId", 1), ("createdAt", -1)])

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop(), name="st-options-engine")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def meta(self) -> dict[str, Any]:
        return {
            "underlyings": ["BTC", "ETH"],
            "resolution": RESOLUTION,
            "defaults": {
                "maxRisk": DEFAULT_MAX_RISK,
                "stPeriod": DEFAULT_ST_PERIOD,
                "stMultiplier": DEFAULT_ST_MULTIPLIER,
                "emaLength": DEFAULT_EMA_LENGTH,
                "minPremiumPct": DEFAULT_MIN_PREMIUM_PCT,
                "stopLossPct": DEFAULT_STOP_LOSS_PCT,
                "takeProfitPct": DEFAULT_TAKE_PROFIT_PCT,
                "breakevenDecayPct": DEFAULT_BREAKEVEN_DECAY_PCT,
                "pairHedgeDecayPct": DEFAULT_LIVE_PAIR_HEDGE_DECAY_PCT,
                "maxStDistancePct": DEFAULT_MAX_ST_DISTANCE_PCT,
            },
            "fixed": {
                "otmDepth": 3,
                "itmDepth": 3,
                "expiryOffsets": ["T0", "T1"],
                "t0EntryCutoffIst": "10:30",
                "forceCloseIst": "17:15",
                "settlementIst": "17:30",
                "warmupDays": WARMUP_DAYS,
            },
        }

    async def get_config(self, user: dict[str, Any]) -> dict[str, Any]:
        doc = await self._config.find_one({"userId": user["id"]})
        if not doc:
            doc = _default_config(user["id"])
            await self._config.insert_one(doc)
        return config_to_view(doc)

    async def patch_config(self, user: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        current = await self.get_config(user)
        updates: dict[str, Any] = {"updatedAt": _now()}
        if patch.get("underlying") is not None:
            updates["underlying"] = normalize_underlying(str(patch["underlying"]))
        if patch.get("maxRisk") is not None:
            risk = float(patch["maxRisk"])
            if risk <= 0:
                raise http_error(400, "maxRisk must be > 0")
            updates["maxRisk"] = risk
        if patch.get("stPeriod") is not None:
            period = int(patch["stPeriod"])
            if period < 1:
                raise http_error(400, "stPeriod must be >= 1")
            updates["stPeriod"] = period
        if patch.get("stMultiplier") is not None:
            mult = float(patch["stMultiplier"])
            if mult <= 0:
                raise http_error(400, "stMultiplier must be > 0")
            updates["stMultiplier"] = mult
        if patch.get("emaLength") is not None:
            length = int(patch["emaLength"])
            if length < 1:
                raise http_error(400, "emaLength must be >= 1")
            updates["emaLength"] = length
        if patch.get("minPremiumPct") is not None:
            pct = float(patch["minPremiumPct"])
            if pct <= 0:
                raise http_error(400, "minPremiumPct must be > 0")
            updates["minPremiumPct"] = pct
        if patch.get("stopLossPct") is not None:
            pct = float(patch["stopLossPct"])
            if pct <= 0:
                raise http_error(400, "stopLossPct must be > 0")
            updates["stopLossPct"] = pct
        if patch.get("takeProfitPct") is not None:
            pct = float(patch["takeProfitPct"])
            if pct <= 0 or pct >= 100:
                raise http_error(400, "takeProfitPct must be > 0 and < 100")
            updates["takeProfitPct"] = pct
        _apply_breakeven_decay_patch(updates, patch)
        _apply_pair_hedge_decay_patch(updates, patch)
        _apply_max_st_distance_patch(updates, patch)

        await self._config.update_one(
            {"userId": user["id"]},
            {"$set": updates, "$setOnInsert": {"userId": user["id"], "enabled": current["enabled"]}},
            upsert=True,
        )
        view = await self.get_config(user)
        await self._publish_session(user["id"])
        # Hot-toggle: apply hedge decay immediately without waiting for the 15s engine tick.
        if view.get("enabled") and "pairHedgeDecayPct" in updates:
            try:
                await self._manage_open_premiums(user["id"], view)
                await self._publish_session(user["id"])
            except Exception:
                log.exception(
                    "ST Options: immediate hedge manage after config patch failed user=%s",
                    user["id"],
                )
        return view

    async def get_backtest_config(self, user: dict[str, Any]) -> dict[str, Any]:
        doc = await self._bt_config.find_one({"userId": user["id"]})
        if not doc:
            doc = _default_backtest_config(user["id"])
            await self._bt_config.insert_one(doc)
        return backtest_config_to_view(doc)

    async def patch_backtest_config(self, user: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        updates: dict[str, Any] = {"updatedAt": _now()}
        if patch.get("underlying") is not None:
            updates["underlying"] = normalize_underlying(str(patch["underlying"]))
        if patch.get("maxRisk") is not None:
            risk = float(patch["maxRisk"])
            if risk <= 0:
                raise http_error(400, "maxRisk must be > 0")
            updates["maxRisk"] = risk
        if patch.get("stPeriod") is not None:
            period = int(patch["stPeriod"])
            if period < 1:
                raise http_error(400, "stPeriod must be >= 1")
            updates["stPeriod"] = period
        if patch.get("stMultiplier") is not None:
            mult = float(patch["stMultiplier"])
            if mult <= 0:
                raise http_error(400, "stMultiplier must be > 0")
            updates["stMultiplier"] = mult
        if patch.get("emaLength") is not None:
            length = int(patch["emaLength"])
            if length < 1:
                raise http_error(400, "emaLength must be >= 1")
            updates["emaLength"] = length
        if patch.get("minPremiumPct") is not None:
            pct = float(patch["minPremiumPct"])
            if pct <= 0:
                raise http_error(400, "minPremiumPct must be > 0")
            updates["minPremiumPct"] = pct
        if patch.get("stopLossPct") is not None:
            pct = float(patch["stopLossPct"])
            if pct <= 0:
                raise http_error(400, "stopLossPct must be > 0")
            updates["stopLossPct"] = pct
        if patch.get("takeProfitPct") is not None:
            pct = float(patch["takeProfitPct"])
            if pct <= 0 or pct >= 100:
                raise http_error(400, "takeProfitPct must be > 0 and < 100")
            updates["takeProfitPct"] = pct
        _apply_breakeven_decay_patch(updates, patch)
        if patch.get("dynamicSizingEnabled") is not None:
            updates["dynamicSizingEnabled"] = bool(patch["dynamicSizingEnabled"])
        for key, minimum in (
            ("dynAfterLosses", 0),
            ("dynAfterProfits", 0),
        ):
            if patch.get(key) is not None:
                value = int(patch[key])
                if value < minimum:
                    raise http_error(400, f"{key} must be >= {minimum}")
                updates[key] = value
        for key, minimum in (
            ("dynIncreasePct", 0),
            ("dynDecreasePct", 0),
            ("dynMaxRiskPct", 100),
        ):
            if patch.get(key) is not None:
                value = float(patch[key])
                if value < minimum:
                    raise http_error(400, f"{key} must be >= {minimum}")
                updates[key] = value
        if patch.get("strikeSelectMode") is not None:
            mode = str(patch["strikeSelectMode"]).strip().lower()
            if mode not in VALID_STRIKE_SELECT_MODES:
                raise http_error(400, f"strikeSelectMode must be one of {sorted(VALID_STRIKE_SELECT_MODES)}")
            updates["strikeSelectMode"] = mode
        if patch.get("strikeType") is not None:
            try:
                parse_strike_type(str(patch["strikeType"]))
            except ValueError as exc:
                raise http_error(400, str(exc)) from exc
            updates["strikeType"] = str(patch["strikeType"]).strip().upper()
        if patch.get("minPremiumAbs") is not None:
            abs_prem = float(patch["minPremiumAbs"])
            if abs_prem <= 0:
                raise http_error(400, "minPremiumAbs must be > 0")
            updates["minPremiumAbs"] = abs_prem
        if patch.get("oneTradePerFormation") is not None:
            updates["oneTradePerFormation"] = bool(patch["oneTradePerFormation"])
        if patch.get("skipSetupsAfterTarget") is not None:
            skips = int(patch["skipSetupsAfterTarget"])
            if skips < 0:
                raise http_error(400, "skipSetupsAfterTarget must be >= 0")
            updates["skipSetupsAfterTarget"] = skips
        _apply_max_st_distance_patch(updates, patch)
        if patch.get("pairHedgeEnabled") is not None:
            updates["pairHedgeEnabled"] = bool(patch["pairHedgeEnabled"])
        if patch.get("pairHedgeMode") is not None:
            mode = str(patch["pairHedgeMode"]).strip().lower()
            if mode not in VALID_PAIR_HEDGE_MODES:
                raise http_error(400, f"pairHedgeMode must be one of {sorted(VALID_PAIR_HEDGE_MODES)}")
            updates["pairHedgeMode"] = mode
        if patch.get("pairHedgeDecayPct") is not None:
            decay = float(patch["pairHedgeDecayPct"])
            if decay < 0 or decay >= 100:
                raise http_error(400, "pairHedgeDecayPct must be >= 0 and < 100")
            updates["pairHedgeDecayPct"] = decay

        await self._bt_config.update_one(
            {"userId": user["id"]},
            {"$set": updates, "$setOnInsert": {"userId": user["id"]}},
            upsert=True,
        )
        return await self.get_backtest_config(user)

    def _run_list_item(self, doc: dict[str, Any]) -> dict[str, Any]:
        summary = (doc.get("result") or {}).get("summary") or {}
        settings = doc.get("settings") or {}
        return {
            "id": str(doc["_id"]),
            "createdAt": _iso_utc(doc.get("createdAt")),
            "status": doc.get("status", "completed"),
            "from": settings.get("from"),
            "to": settings.get("to"),
            "underlying": settings.get("underlying"),
            "totalTrades": summary.get("totalTrades"),
            "totalPnl": summary.get("totalPnl"),
            "settings": settings,
        }

    async def list_backtest_runs(self, user: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
        cursor = (
            self._bt_runs.find({"userId": user["id"]})
            .sort("createdAt", -1)
            .limit(min(int(limit), BACKTEST_RUNS_KEEP))
        )
        docs = await cursor.to_list(length=min(int(limit), BACKTEST_RUNS_KEEP))
        return [self._run_list_item(doc) for doc in docs]

    async def get_backtest_run(self, user: dict[str, Any], run_id: str) -> dict[str, Any]:
        try:
            oid = ObjectId(run_id)
        except Exception as exc:
            raise http_error(400, "Invalid run id") from exc
        doc = await self._bt_runs.find_one({"_id": oid, "userId": user["id"]})
        if not doc:
            raise http_error(404, "Backtest run not found")
        return {
            "id": str(doc["_id"]),
            "createdAt": _iso_utc(doc.get("createdAt")),
            "status": doc.get("status", "completed"),
            "settings": doc.get("settings") or {},
            "result": doc.get("result"),
            "error": doc.get("error"),
        }

    async def delete_backtest_run(self, user: dict[str, Any], run_id: str) -> dict[str, Any]:
        try:
            oid = ObjectId(run_id)
        except Exception as exc:
            raise http_error(400, "Invalid run id") from exc
        result = await self._bt_runs.delete_one({"_id": oid, "userId": user["id"]})
        if result.deleted_count == 0:
            raise http_error(404, "Backtest run not found")
        return {"ok": True, "id": run_id}

    async def _persist_backtest_run(
        self,
        user_id: str,
        *,
        settings: dict[str, Any],
        result: dict[str, Any] | None,
        status: str,
        error: str | None = None,
    ) -> str | None:
        doc = {
            "userId": user_id,
            "createdAt": _now(),
            "status": status,
            "settings": settings,
            "result": result,
            "error": error,
        }
        inserted = await self._bt_runs.insert_one(doc)
        run_id = str(inserted.inserted_id)
        keep_docs = (
            await self._bt_runs.find({"userId": user_id}, {"_id": 1})
            .sort("createdAt", -1)
            .limit(BACKTEST_RUNS_KEEP)
            .to_list(length=BACKTEST_RUNS_KEEP)
        )
        keep_ids = [d["_id"] for d in keep_docs]
        if keep_ids:
            await self._bt_runs.delete_many({"userId": user_id, "_id": {"$nin": keep_ids}})
        return run_id

    async def start_live(self, user: dict[str, Any], settings_patch: dict[str, Any] | None = None) -> dict[str, Any]:
        if not user.get("selectedAccountId"):
            raise http_error(400, "Select a trading account before starting ST Options.")
        # Apply settings + enable in one write so a prior PATCH publish cannot race the UI.
        updates: dict[str, Any] = {"enabled": True, "updatedAt": _now()}
        patch = settings_patch or {}
        if patch.get("underlying") is not None:
            updates["underlying"] = normalize_underlying(str(patch["underlying"]))
        if patch.get("maxRisk") is not None:
            risk = float(patch["maxRisk"])
            if risk <= 0:
                raise http_error(400, "maxRisk must be > 0")
            updates["maxRisk"] = risk
        if patch.get("stPeriod") is not None:
            period = int(patch["stPeriod"])
            if period < 1:
                raise http_error(400, "stPeriod must be >= 1")
            updates["stPeriod"] = period
        if patch.get("stMultiplier") is not None:
            mult = float(patch["stMultiplier"])
            if mult <= 0:
                raise http_error(400, "stMultiplier must be > 0")
            updates["stMultiplier"] = mult
        if patch.get("emaLength") is not None:
            length = int(patch["emaLength"])
            if length < 1:
                raise http_error(400, "emaLength must be >= 1")
            updates["emaLength"] = length
        if patch.get("minPremiumPct") is not None:
            pct = float(patch["minPremiumPct"])
            if pct <= 0:
                raise http_error(400, "minPremiumPct must be > 0")
            updates["minPremiumPct"] = pct
        if patch.get("stopLossPct") is not None:
            pct = float(patch["stopLossPct"])
            if pct <= 0:
                raise http_error(400, "stopLossPct must be > 0")
            updates["stopLossPct"] = pct
        if patch.get("takeProfitPct") is not None:
            pct = float(patch["takeProfitPct"])
            if pct <= 0 or pct >= 100:
                raise http_error(400, "takeProfitPct must be > 0 and < 100")
            updates["takeProfitPct"] = pct
        _apply_breakeven_decay_patch(updates, patch)
        _apply_pair_hedge_decay_patch(updates, patch)
        _apply_max_st_distance_patch(updates, patch)

        on_insert = {
            k: v for k, v in _default_config(user["id"]).items() if k not in updates
        }
        await self._config.update_one(
            {"userId": user["id"]},
            {"$set": updates, "$setOnInsert": on_insert},
            upsert=True,
        )
        config = await self.get_config(user)
        await self._market.ensure_symbols({perp_symbol(config["underlying"])})
        tech = (
            f"Engine started · user={user['id']} underlying={config['underlying']} "
            f"maxRisk={config['maxRisk']} minPremiumPct={config['minPremiumPct']} "
            f"slPct={config['stopLossPct']} tpPct={config['takeProfitPct']} "
            f"hedgeDecay={config['pairHedgeDecayPct']} maxStDist={config['maxStDistancePct']} "
            f"st={config['stPeriod']}/{config['stMultiplier']} ema={config['emaLength']}"
        )
        log.info("ST Options: %s", tech)
        self._push_activity(
            user["id"],
            tech,
            user_message=(
                f"Strategy turned on for {config['underlying']} "
                f"(max risk {config['maxRisk']})"
            ),
        )
        await self._publish_session(user["id"])
        return await self.live_snapshot(user)

    async def stop_live(self, user: dict[str, Any]) -> dict[str, Any]:
        async def _close_all_opens() -> int:
            # Promote any filled pending entries first so SL/TP attach, then flatten.
            config = await self.get_config(user)
            await self._reconcile_pending_entries(user["id"], config)
            open_trades = await self._list_trade_docs(user["id"], status=STATUS_OPEN)
            closed = 0
            for doc in open_trades:
                if await self._close_live_trade(
                    user["id"], doc, reason="manual_stop", exit_premium=None
                ):
                    closed += 1
            pending = await self._list_trade_docs(user["id"], status=STATUS_PENDING_ENTRY)
            for doc in pending:
                symbol = str(doc.get("optionSymbol") or "")
                still_short = False
                if symbol:
                    try:
                        api_key, api_secret = await self._trade_credentials(user["id"], doc)
                        still_short = (
                            await self._find_short_option_position(api_key, api_secret, symbol)
                            is not None
                        )
                    except Exception:
                        still_short = True  # keep pending if we cannot verify flat
                if still_short:
                    log.warning(
                        "ST Options stop: pending entry still short on broker user=%s symbol=%s",
                        user["id"],
                        symbol,
                    )
                    continue
                await self._trades.delete_one(
                    {"_id": doc["_id"], "status": STATUS_PENDING_ENTRY}
                )
            return closed

        await _close_all_opens()
        remaining = await self._list_trade_docs(user["id"], status=STATUS_OPEN)
        if remaining:
            log.warning(
                "ST Options stop: %s open leg(s) remain for %s — retrying once",
                len(remaining),
                user["id"],
            )
            await _close_all_opens()

        remaining = await self._list_trade_docs(user["id"], status=STATUS_OPEN)
        await self._config.update_one(
            {"userId": user["id"]},
            {"$set": {"enabled": False, "updatedAt": _now()}},
            upsert=True,
        )
        close_failures = [
            {
                "tradeId": str(d.get("_id", "")),
                "symbol": d.get("optionSymbol"),
                "reason": d.get("closeError") or "close_failed",
            }
            for d in remaining
        ]
        if remaining:
            tech = (
                f"Engine stopped · user={user['id']} leftovers={len(remaining)} "
                f"symbols={[d.get('optionSymbol') for d in remaining]}"
            )
            log.warning("ST Options: %s", tech)
            self._push_activity(
                user["id"],
                tech,
                user_message=f"Strategy turned off — {len(remaining)} position(s) still open (close failed)",
                level="warn",
            )
        else:
            tech = f"Engine stopped · user={user['id']} flat"
            log.info("ST Options: %s", tech)
            self._push_activity(
                user["id"],
                tech,
                user_message="Strategy turned off — no open positions",
            )
        await self._publish_session(user["id"])
        snapshot = await self.live_snapshot(user)
        snapshot["closeFailures"] = close_failures
        return snapshot

    async def live_snapshot(self, user: dict[str, Any]) -> dict[str, Any]:
        config = await self.get_config(user)
        active = await self._list_trades(
            user["id"], status=[STATUS_OPEN, STATUS_PENDING_ENTRY]
        )
        indicator = None
        with contextlib.suppress(Exception):
            indicator = await self._indicator_snapshot(config)
        status = await self._engine_status(user["id"], config, indicator, active)
        job = self._backtest_jobs.get(user["id"])
        return {
            "type": "st_options_session",
            "topic": "st_options",
            "config": config,
            "active": active,
            "indicator": indicator,
            "status": status,
            "backtestJob": self._job_public(job) if job else None,
        }

    async def history(
        self,
        user: dict[str, Any],
        *,
        limit: int = HISTORY_DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        page_size = max(1, min(int(limit or HISTORY_DEFAULT_LIMIT), HISTORY_MAX_LIMIT))
        query: dict[str, Any] = {"userId": user["id"], "status": STATUS_CLOSED}
        if cursor:
            exit_time, oid = _decode_history_cursor(cursor)
            query["$or"] = [
                {"exitTime": {"$lt": exit_time}},
                {"exitTime": exit_time, "_id": {"$lt": oid}},
            ]
        mongo_cursor = (
            self._trades.find(query)
            .sort([("exitTime", -1), ("_id", -1)])
            .limit(page_size + 1)
        )
        docs = [doc async for doc in mongo_cursor]
        has_more = len(docs) > page_size
        if has_more:
            docs = docs[:page_size]
        next_cursor = None
        if has_more and docs:
            last = docs[-1]
            next_cursor = _encode_history_cursor(last.get("exitTime"), last.get("_id"))
        return {
            "trades": [trade_to_view(doc) for doc in docs],
            "nextCursor": next_cursor,
            "hasMore": has_more,
            "summary": await self._closed_trades_summary(user["id"]),
        }

    async def _closed_trades_summary(self, user_id: str) -> dict[str, Any]:
        pipeline: list[dict[str, Any]] = [
            {"$match": {"userId": user_id, "status": STATUS_CLOSED}},
            {
                "$group": {
                    "_id": None,
                    "trades": {"$sum": 1},
                    "long": {
                        "$sum": {"$cond": [{"$eq": ["$direction", "LONG"]}, 1, 0]},
                    },
                    "short": {
                        "$sum": {"$cond": [{"$eq": ["$direction", "SHORT"]}, 1, 0]},
                    },
                    "profitCount": {
                        "$sum": {"$cond": [{"$gt": ["$pnl", 0]}, 1, 0]},
                    },
                    "lossCount": {
                        "$sum": {"$cond": [{"$lt": ["$pnl", 0]}, 1, 0]},
                    },
                    "maxProfit": {
                        "$max": {
                            "$cond": [{"$gt": ["$pnl", 0]}, "$pnl", 0],
                        }
                    },
                    "maxLoss": {
                        "$min": {
                            "$cond": [{"$lt": ["$pnl", 0]}, "$pnl", 0],
                        }
                    },
                    "totalProfit": {
                        "$sum": {
                            "$cond": [{"$gt": ["$pnl", 0]}, "$pnl", 0],
                        }
                    },
                    "totalLoss": {
                        "$sum": {
                            "$cond": [{"$lt": ["$pnl", 0]}, "$pnl", 0],
                        }
                    },
                }
            },
        ]
        rows = await self._trades.aggregate(pipeline).to_list(length=1)
        if not rows:
            return _empty_closed_summary()
        row = rows[0]
        total_profit = float(row.get("totalProfit") or 0)
        total_loss = float(row.get("totalLoss") or 0)
        loss_abs = abs(total_loss)
        return {
            "trades": int(row.get("trades") or 0),
            "long": int(row.get("long") or 0),
            "short": int(row.get("short") or 0),
            "profitCount": int(row.get("profitCount") or 0),
            "lossCount": int(row.get("lossCount") or 0),
            "maxProfit": float(row.get("maxProfit") or 0),
            "maxLoss": float(row.get("maxLoss") or 0),
            "totalProfit": total_profit,
            "totalLoss": total_loss,
            "totalPnl": total_profit + total_loss,
            "lossToProfit": (loss_abs / total_profit) if total_profit > 0 else None,
        }

    async def submit_backtest(self, user: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        from_raw = body.get("from") or body.get("fromDate")
        to_raw = body.get("to") or body.get("toDate")
        if not from_raw or not to_raw:
            raise http_error(400, "from and to dates are required")
        try:
            from_date = date.fromisoformat(str(from_raw)[:10])
            to_date = date.fromisoformat(str(to_raw)[:10])
        except ValueError as exc:
            raise http_error(400, "Invalid from/to date") from exc
        if to_date < from_date:
            raise http_error(400, "to must be on or after from")
        be_raw = body.get("breakevenDecayPct")
        if be_raw is not None:
            be_pct = float(be_raw)
            if be_pct < 0 or be_pct >= 100:
                raise http_error(400, "breakevenDecayPct must be >= 0 and < 100 (0 = off)")
        else:
            be_pct = DEFAULT_BREAKEVEN_DECAY_PCT

        dyn = _dynamic_sizing_from_body(body)
        strike_mode = str(body.get("strikeSelectMode") or DEFAULT_STRIKE_SELECT_MODE).strip().lower()
        if strike_mode not in VALID_STRIKE_SELECT_MODES:
            raise http_error(400, f"strikeSelectMode must be one of {sorted(VALID_STRIKE_SELECT_MODES)}")
        strike_type = str(body.get("strikeType") or DEFAULT_STRIKE_TYPE).strip().upper()
        try:
            parse_strike_type(strike_type)
        except ValueError as exc:
            raise http_error(400, str(exc)) from exc
        min_premium_abs = float(body.get("minPremiumAbs", DEFAULT_MIN_PREMIUM_ABS) or DEFAULT_MIN_PREMIUM_ABS)
        if min_premium_abs <= 0:
            raise http_error(400, "minPremiumAbs must be > 0")
        one_trade_per_formation = bool(body.get("oneTradePerFormation", False))
        skip_after_target = int(
            body.get("skipSetupsAfterTarget", DEFAULT_SKIP_SETUPS_AFTER_TARGET)
            if body.get("skipSetupsAfterTarget") is not None
            else DEFAULT_SKIP_SETUPS_AFTER_TARGET
        )
        if skip_after_target < 0:
            raise http_error(400, "skipSetupsAfterTarget must be >= 0")
        max_st_distance_pct = float(
            body.get("maxStDistancePct", DEFAULT_MAX_ST_DISTANCE_PCT)
            if body.get("maxStDistancePct") is not None
            else DEFAULT_MAX_ST_DISTANCE_PCT
        )
        if max_st_distance_pct < 0:
            raise http_error(400, "maxStDistancePct must be >= 0 (0 = off)")
        pair_hedge_enabled = bool(body.get("pairHedgeEnabled", False))
        pair_hedge_mode = normalize_pair_hedge_mode(body.get("pairHedgeMode"))
        if body.get("pairHedgeMode") is not None:
            raw_mode = str(body.get("pairHedgeMode")).strip().lower()
            if raw_mode not in VALID_PAIR_HEDGE_MODES:
                raise http_error(400, f"pairHedgeMode must be one of {sorted(VALID_PAIR_HEDGE_MODES)}")
            pair_hedge_mode = raw_mode
        pair_hedge_decay = float(
            body.get("pairHedgeDecayPct", DEFAULT_PAIR_HEDGE_DECAY_PCT)
            if body.get("pairHedgeDecayPct") is not None
            else DEFAULT_PAIR_HEDGE_DECAY_PCT
        )
        if pair_hedge_decay < 0 or pair_hedge_decay >= 100:
            raise http_error(400, "pairHedgeDecayPct must be >= 0 and < 100")
        max_risk = float(body.get("maxRisk", DEFAULT_MAX_RISK) or DEFAULT_MAX_RISK)
        if max_risk <= 0:
            raise http_error(400, "maxRisk must be > 0")

        job_id = str(uuid.uuid4())
        job = {
            "id": job_id,
            "userId": user["id"],
            "status": "processing",
            "progress": 0,
            "stage": "starting",
            "trace": [],
            "result": None,
            "error": None,
            "runId": None,
            "createdAt": _now().isoformat(),
        }
        self._backtest_jobs[user["id"]] = job
        await self._publish_session(user["id"])
        asyncio.create_task(
            self._run_backtest_job(
                user["id"],
                job_id,
                underlying=normalize_underlying(str(body.get("underlying") or "BTC")),
                max_risk=max_risk,
                st_period=int(body.get("stPeriod", DEFAULT_ST_PERIOD)),
                st_multiplier=float(body.get("stMultiplier", DEFAULT_ST_MULTIPLIER)),
                ema_length=int(body.get("emaLength", DEFAULT_EMA_LENGTH)),
                min_premium_pct=float(body.get("minPremiumPct", DEFAULT_MIN_PREMIUM_PCT)),
                stop_loss_pct=float(body.get("stopLossPct") or DEFAULT_STOP_LOSS_PCT),
                take_profit_pct=float(body.get("takeProfitPct") or DEFAULT_TAKE_PROFIT_PCT),
                breakeven_decay_pct=be_pct,
                dynamic_sizing=dyn,
                strike_select_mode=strike_mode,
                strike_type=strike_type,
                min_premium_abs=min_premium_abs,
                one_trade_per_formation=one_trade_per_formation,
                skip_setups_after_target=skip_after_target,
                max_st_distance_pct=max_st_distance_pct,
                pair_hedge_enabled=pair_hedge_enabled,
                pair_hedge_mode=pair_hedge_mode,
                pair_hedge_decay_pct=pair_hedge_decay,
                from_date=from_date,
                to_date=to_date,
            ),
            name=f"st-options-bt-{job_id[:8]}",
        )
        return {"id": job_id, "status": "processing"}

    def get_backtest_job(self, user: dict[str, Any]) -> dict[str, Any] | None:
        return self._job_public(self._backtest_jobs.get(user["id"]))

    def _job_public(self, job: dict[str, Any] | None) -> dict[str, Any] | None:
        if not job:
            return None
        return {
            "id": job["id"],
            "status": job["status"],
            "progress": job.get("progress", 0),
            "stage": job.get("stage"),
            "trace": (job.get("trace") or [])[-40:],
            "result": job.get("result"),
            "error": job.get("error"),
            "runId": job.get("runId"),
            "createdAt": job.get("createdAt"),
        }

    async def _list_trades(
        self,
        user_id: str,
        *,
        status: str | list[str] | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        docs = await self._list_trade_docs(user_id, status=status, limit=limit)
        return [trade_to_view(doc) for doc in docs]

    async def _list_trade_docs(
        self,
        user_id: str,
        *,
        status: str | list[str] | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"userId": user_id}
        if isinstance(status, list):
            query["status"] = {"$in": status}
        elif status:
            query["status"] = status
        sort_field = (
            "entryTime"
            if status == STATUS_OPEN
            or (isinstance(status, list) and STATUS_OPEN in status)
            or (isinstance(status, list) and STATUS_PENDING_ENTRY in status)
            else "exitTime"
        )
        cursor = self._trades.find(query).sort(sort_field, -1).limit(limit)
        return [doc async for doc in cursor]

    async def _publish_session(self, user_id: str) -> None:
        payload = await self.live_snapshot({"id": user_id})
        self.broadcaster.publish(user_id, payload)

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick_all()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("ST Options engine tick failed")
            await asyncio.sleep(POLL_SECONDS)

    async def _tick_all(self) -> None:
        cursor = self._config.find({"enabled": True})
        async for doc in cursor:
            user_id = doc.get("userId")
            if not user_id:
                continue
            try:
                await self._tick_user(str(user_id), doc)
            except Exception:
                log.exception("ST Options tick failed for user %s", user_id)

    async def _tick_user(self, user_id: str, config_doc: dict[str, Any]) -> None:
        # Re-read Mongo so mid-run PATCH (e.g. pairHedgeDecayPct) applies this tick,
        # not a stale cursor document loaded at the start of _tick_all.
        config = await self.get_config({"id": user_id})
        if not config.get("enabled"):
            return
        self._last_tick_at[user_id] = _now()
        await self._market.ensure_symbols({perp_symbol(config["underlying"])})
        await self._reconcile_pending_entries(user_id, config)
        await self._sync_broker_shorts_with_st(user_id, config)
        await self._force_close_expiring(user_id, config)
        await self._manage_open_premiums(user_id, config)
        await self._process_new_bar(user_id, config)
        await self._publish_session(user_id)


    @staticmethod
    def _exit_reason_user(reason: str) -> str:
        return {
            "st_flip": "market flipped",
            "stop_loss": "stop",
            "take_profit": "target",
            "manual_stop": "closed manually",
            "end_of_data": "end of data",
            "expiry_close": "closed before expiry",
            "expired": "settled at expiry",
            "force_closed": "force closed",
            "max_loss": "max loss",
            "pair_stop": "pair exit",
            "broker_flat": "closed on exchange",
        }.get(str(reason), str(reason).replace("_", " "))

    def _push_activity(
        self,
        user_id: str,
        message: str,
        *,
        user_message: str | None = None,
        level: str = "info",
    ) -> None:
        """Buffer dual activity: technical `message` + plain `userMessage` for Live UI."""
        row = {
            "at": _iso_utc(_now()),
            "level": level,
            "message": message,
            "userMessage": user_message if user_message is not None else message,
        }
        bucket = self._activity.setdefault(user_id, [])
        bucket.append(row)
        if len(bucket) > 40:
            del bucket[:-40]

    async def _engine_status(
        self,
        user_id: str,
        config: dict[str, Any],
        indicator: dict[str, Any] | None,
        active: list[dict[str, Any]],
    ) -> dict[str, Any]:
        now = _now()
        now_ts = int(now.timestamp())
        seconds_to_close = RESOLUTION_SECONDS - (now_ts % RESOLUTION_SECONDS)
        if seconds_to_close == RESOLUTION_SECONDS:
            seconds_to_close = 0
        next_close = now_ts + seconds_to_close
        open_dirs = {str(t.get("direction")) for t in active}
        long_open = "LONG" in open_dirs
        short_open = "SHORT" in open_dirs

        long_ready = False
        short_ready = False
        sentiment = None
        sentiment_label = None
        long_detail = "Waiting for market data"
        short_detail = "Waiting for market data"
        max_st_dist = float(config.get("maxStDistancePct") or 0)
        if indicator and indicator.get("close") is not None and indicator.get("ema") is not None and indicator.get(
            "stLine"
        ) is not None:
            close = float(indicator["close"])
            ema = float(indicator["ema"])
            st_line = float(indicator["stLine"])
            if close > st_line:
                sentiment = "LONG"
                sentiment_label = "up"
            elif close < st_line:
                sentiment = "SHORT"
                sentiment_label = "down"
            dist_ok = max_st_dist <= 0 or (
                close > 0 and abs(close - st_line) / close * 100.0 < max_st_dist
            )
            long_geom = close < ema and close > st_line
            short_geom = close > ema and close < st_line
            long_ready = long_geom and dist_ok
            short_ready = short_geom and dist_ok
            if long_open:
                long_detail = "Long-side trade already open"
            elif long_ready:
                long_detail = "Setup ready — waiting for the next hour to open a long-side trade"
            elif long_geom and not dist_ok:
                long_detail = "Waiting for close nearer the SuperTrend line"
            elif close <= st_line:
                long_detail = "Not active while bias is down"
            elif close >= ema:
                long_detail = "Waiting for a pullback in an up market"
            else:
                long_detail = "Looking for a long-side setup"
            if short_open:
                short_detail = "Short-side trade already open"
            elif short_ready:
                short_detail = "Setup ready — waiting for the next hour to open a short-side trade"
            elif short_geom and not dist_ok:
                short_detail = "Waiting for close nearer the SuperTrend line"
            elif close >= st_line:
                short_detail = "Not active while bias is up"
            elif close <= ema:
                short_detail = "Waiting for a bounce in a down market"
            else:
                short_detail = "Looking for a short-side setup"

        last_bar = self._last_processed_bar.get(user_id)
        last_tick = self._last_tick_at.get(user_id)
        phase = "stopped"
        if config.get("enabled"):
            if active:
                phase = "managing_opens"
            elif long_ready or short_ready:
                phase = "entry_ready"
            else:
                phase = "watching"

        return {
            "enabled": bool(config.get("enabled")),
            "phase": phase,
            "underlying": config.get("underlying"),
            "maxRisk": config.get("maxRisk"),
            "minPremiumPct": config.get("minPremiumPct"),
            "pollSeconds": POLL_SECONDS,
            "lastTickAt": _iso_utc(last_tick),
            "lastProcessedBarTime": last_bar,
            "lastProcessedBarIst": format_ist(last_bar) if last_bar else None,
            "secondsToNextBarClose": seconds_to_close,
            "nextBarCloseIst": format_ist(next_close),
            "sentiment": sentiment,
            "sentimentLabel": sentiment_label,
            "long": {
                "ready": long_ready and not long_open,
                "open": long_open,
                "optionSide": "PUT",
                "label": "Long-side",
                "detail": long_detail,
            },
            "short": {
                "ready": short_ready and not short_open,
                "open": short_open,
                "optionSide": "CALL",
                "label": "Short-side",
                "detail": short_detail,
            },
            "activity": list(self._activity.get(user_id, [])[-16:]),
        }

    async def _indicator_snapshot(self, config: dict[str, Any]) -> dict[str, Any] | None:
        bars = await self._fetch_perp_bars(config["underlying"], end=_now(), days=max(WARMUP_DAYS, 5))
        if not bars:
            return None
        inds = compute_indicator_bars(
            bars,
            st_period=int(config["stPeriod"]),
            st_multiplier=float(config["stMultiplier"]),
            ema_length=int(config["emaLength"]),
        )
        last = next((b for b in reversed(inds) if b.ema is not None and b.st.st_line is not None), None)
        if last is None:
            return None
        return {
            "barTime": last.time,
            "barTimeIst": format_ist(last.time),
            "close": last.close,
            "ema": last.ema,
            "stLine": last.st.st_line,
            "stColour": last.st_colour,
            "stColourChangeTime": format_ist(last.st_colour_change_time),
            "upperBand": last.st.upper_band,
            "lowerBand": last.st.lower_band,
        }

    async def _process_new_bar(self, user_id: str, config: dict[str, Any]) -> None:
        bars = await self._fetch_perp_bars(config["underlying"], end=_now(), days=WARMUP_DAYS)
        if len(bars) < 3:
            return
        now_ts = int(_now().timestamp())
        closed_bars = [b for b in bars if b.time + RESOLUTION_SECONDS <= now_ts]
        if not closed_bars:
            return
        last = closed_bars[-1]
        prev_processed = self._last_processed_bar.get(user_id)
        if prev_processed is not None and last.time <= prev_processed:
            return

        inds = compute_indicator_bars(
            closed_bars,
            st_period=int(config["stPeriod"]),
            st_multiplier=float(config["stMultiplier"]),
            ema_length=int(config["emaLength"]),
        )
        bar = inds[-1]
        self._last_processed_bar[user_id] = last.time
        max_st_dist = float(config.get("maxStDistancePct") or 0)
        long_r = entry_ready(bar, "LONG") and st_distance_within(bar, max_st_dist)  # type: ignore[arg-type]
        short_r = entry_ready(bar, "SHORT") and st_distance_within(bar, max_st_dist)  # type: ignore[arg-type]
        tech = (
            f"Processed 1H bar user={user_id} time={format_ist(last.time)} close={bar.close:.2f} "
            f"ema={bar.ema} stLine={bar.st.st_line} stColour={bar.st_colour} "
            f"longReady={long_r} shortReady={short_r}"
        )
        log.info("ST Options: %s", tech)
        self._push_activity(
            user_id,
            tech,
            user_message=f"Checked the latest hour ({format_ist(last.time)})",
        )

        for direction in ("LONG", "SHORT"):
            open_doc = await self._trades.find_one(
                {
                    "userId": user_id,
                    "status": {"$in": list(_ACTIVE_TRADE_STATUSES)},
                    "direction": direction,
                }
            )
            if open_doc and open_doc.get("status") == STATUS_OPEN and opposite_st_exit(
                direction, bar
            ):  # type: ignore[arg-type]
                await self._close_live_trade(user_id, open_doc, reason="st_flip", exit_premium=None)

        for direction in ("LONG", "SHORT"):
            existing = await self._trades.find_one(
                {
                    "userId": user_id,
                    "status": {"$in": list(_ACTIVE_TRADE_STATUSES)},
                    "direction": direction,
                }
            )
            if existing:
                continue
            if not entry_ready(bar, direction):  # type: ignore[arg-type]
                continue
            if not st_distance_within(bar, max_st_dist):
                side_label = "long-side" if direction == "LONG" else "short-side"
                tech = (
                    f"Skip ST distance user={user_id} direction={direction} "
                    f"bar={format_ist(last.time)} maxPct={max_st_dist}"
                )
                log.info("ST Options: %s", tech)
                self._push_activity(
                    user_id,
                    tech,
                    user_message=f"Skipped {side_label} setup — close too far from SuperTrend",
                )
                continue
            side_label = "long-side" if direction == "LONG" else "short-side"
            tech = f"Entry signal user={user_id} direction={direction} bar={format_ist(last.time)} close={bar.close}"
            log.info("ST Options: %s", tech)
            self._push_activity(
                user_id,
                tech,
                user_message=f"Setup ready for a {side_label} trade",
            )
            await self._open_live_trade(user_id, config, bar, direction)  # type: ignore[arg-type]

    async def _clear_bracket_bookkeeping(self, doc: dict[str, Any]) -> None:
        await self._trades.update_one(
            {"_id": doc["_id"]},
            {
                "$set": {
                    "bracketAttached": False,
                    "updatedAt": _now(),
                },
                "$unset": {
                    "stopOrderId": "",
                    "takeProfitOrderId": "",
                },
            },
        )
        doc["bracketAttached"] = False
        doc.pop("stopOrderId", None)
        doc.pop("takeProfitOrderId", None)

    async def _resolve_bracket_ids(
        self,
        user_id: str,
        doc: dict[str, Any],
        api_key: str,
        api_secret: str,
    ) -> tuple[Any, Any]:
        stop_id = doc.get("stopOrderId")
        target_id = doc.get("takeProfitOrderId")
        symbol = str(doc.get("optionSymbol") or "")
        if (not stop_id or not target_id) and symbol:
            legs = await self._delta.find_bracket_legs(api_key, api_secret, symbol)
            stop_id = stop_id or legs.stop_loss_order_id
            target_id = target_id or legs.take_profit_order_id
            if stop_id or target_id:
                doc["stopOrderId"] = stop_id
                doc["takeProfitOrderId"] = target_id
                await self._trades.update_one(
                    {"_id": doc["_id"], "status": STATUS_OPEN},
                    {
                        "$set": {
                            "stopOrderId": stop_id,
                            "takeProfitOrderId": target_id,
                            "bracketAttached": True,
                            "updatedAt": _now(),
                        },
                        "$unset": {"bracketError": ""},
                    },
                )
        return stop_id, target_id

    async def _lookup_cover_fill_price(
        self,
        api_key: str,
        api_secret: str,
        symbol: str,
        *,
        after_ts: int | None = None,
    ) -> float | None:
        """Most recent buy (cover) fill price for symbol, optionally after entry unix ts."""
        want = normalize_symbol(symbol)
        try:
            fills = await self._delta.fetch_fills(api_key, api_secret, page_size=50)
        except Exception:
            log.exception("ST Options: fetch_fills failed while resolving exit symbol=%s", want)
            return None
        best_price: float | None = None
        best_key: tuple[int, int] | None = None
        for idx, fill in enumerate(fills or []):
            if not isinstance(fill, dict):
                continue
            pos_symbol = normalize_symbol(
                str(fill.get("product_symbol") or fill.get("symbol") or "")
            )
            if pos_symbol != want:
                continue
            side = str(fill.get("side") or "").lower()
            if side not in {"buy", "bid"}:
                continue
            raw_px = (
                fill.get("price")
                or fill.get("fill_price")
                or fill.get("average_fill_price")
            )
            try:
                price = float(raw_px) if raw_px is not None else None
            except (TypeError, ValueError):
                price = None
            if price is None or price <= 0:
                continue
            fill_ts: int | None = None
            for key in ("created_at", "timestamp", "time"):
                raw_ts = fill.get(key)
                if raw_ts is None:
                    continue
                try:
                    if isinstance(raw_ts, (int, float)):
                        fill_ts = int(raw_ts)
                        if fill_ts > 10_000_000_000:
                            fill_ts //= 1000
                    else:
                        fill_ts = int(datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00")).timestamp())
                    break
                except (TypeError, ValueError):
                    continue
            if after_ts is not None and fill_ts is not None and fill_ts < int(after_ts):
                continue
            # Prefer newest fill; when timestamps missing, prefer earlier list rows (API newest-first).
            key = (fill_ts if fill_ts is not None else 0, -idx)
            if best_key is None or key > best_key:
                best_key = key
                best_price = price
        return best_price

    async def _maybe_close_if_broker_flat(self, user_id: str, doc: dict[str, Any]) -> bool:
        """If the short is gone on Delta, close the ST trade with fill-based PnL."""
        if doc.get("status") != STATUS_OPEN:
            return False
        symbol = str(doc.get("optionSymbol") or "")
        if not symbol:
            return False
        try:
            api_key, api_secret = await self._trade_credentials(user_id, doc)
        except Exception:
            log.exception(
                "ST Options: broker-flat credentials failed user=%s symbol=%s",
                user_id,
                symbol,
            )
            return False
        still_short = await self._find_short_option_position(api_key, api_secret, symbol)
        if still_short is not None:
            return False

        after_ts = doc.get("entryTime")
        try:
            after_i = int(after_ts) if after_ts is not None else None
        except (TypeError, ValueError):
            after_i = None
        fill_px = await self._lookup_cover_fill_price(
            api_key, api_secret, symbol, after_ts=after_i
        )
        exit_px = fill_px
        if exit_px is None:
            live = doc.get("livePremium")
            entry = doc.get("premiumReceived")
            exit_px = float(live if live is not None else entry or 0)

        # If hedge still open on our books but already flat on broker, resolve its exit too.
        hedge_exit: float | None = None
        hedge_broker_reduce = False
        if _hedge_is_open(doc) and doc.get("hedgeSymbol"):
            hedge_sym = str(doc["hedgeSymbol"])
            hedge_short = await self._find_short_option_position(
                api_key, api_secret, hedge_sym
            )
            if hedge_short is None:
                hedge_after = doc.get("hedgeEntryTime") or after_i
                try:
                    hedge_after_i = int(hedge_after) if hedge_after is not None else after_i
                except (TypeError, ValueError):
                    hedge_after_i = after_i
                hedge_exit = await self._lookup_cover_fill_price(
                    api_key, api_secret, hedge_sym, after_ts=hedge_after_i
                )
                hedge_broker_reduce = False
            else:
                hedge_broker_reduce = True

        await self._record_broker_bracket_exit(
            user_id,
            doc,
            reason="broker_flat",
            exit_price=float(exit_px),
            close_order_id=0,
            hedge_exit_premium=hedge_exit,
            hedge_broker_reduce=hedge_broker_reduce,
        )
        return True

    async def _record_fill_from_bracket(
        self,
        user_id: str,
        doc: dict[str, Any],
        *,
        reason: str,
        triggered_order: Any,
        sibling_id: Any,
        api_key: str,
        api_secret: str,
    ) -> None:
        fallback_price = (
            doc.get("stopPremium") if reason == "stop_loss" else doc.get("targetPremium")
        )
        avg = getattr(triggered_order, "average_fill_price", None)
        if avg is None:
            after_ts = doc.get("entryTime")
            try:
                after_i = int(after_ts) if after_ts is not None else None
            except (TypeError, ValueError):
                after_i = None
            avg = await self._lookup_cover_fill_price(
                api_key,
                api_secret,
                str(doc.get("optionSymbol") or ""),
                after_ts=after_i,
            )
        exit_price = float(
            avg
            or fallback_price
            or doc.get("livePremium")
            or doc.get("premiumReceived")
            or 0
        )
        if sibling_id:
            with contextlib.suppress(Exception):
                sibling = await self._delta.fetch_order(api_key, api_secret, int(sibling_id))
                if _is_bracket_pending(sibling):
                    await self._delta.cancel_order(api_key, api_secret, int(sibling_id))
        await self._record_broker_bracket_exit(
            user_id,
            doc,
            reason=reason,
            exit_price=exit_price,
            close_order_id=int(getattr(triggered_order, "id", 0) or 0),
        )

    async def _reconcile_broker_bracket(
        self,
        user_id: str,
        doc: dict[str, Any],
    ) -> str:
        """Return closed, protected, or fallback after checking broker bracket legs."""
        if not (
            doc.get("bracketAttached")
            or doc.get("stopOrderId")
            or doc.get("takeProfitOrderId")
        ):
            return "fallback"

        try:
            api_key, api_secret = await self._trade_credentials(user_id, doc)
            stop_id, target_id = await self._resolve_bracket_ids(
                user_id, doc, api_key, api_secret
            )
            symbol = str(doc.get("optionSymbol") or "")

            # No IDs: cannot reconcile fills; soft-monitor instead of leaving Mongo stuck.
            if not stop_id and not target_id:
                await self._clear_bracket_bookkeeping(doc)
                return "fallback"

            stop_order = (
                await self._delta.fetch_order(api_key, api_secret, int(stop_id))
                if stop_id
                else None
            )
            target_order = (
                await self._delta.fetch_order(api_key, api_secret, int(target_id))
                if target_id
                else None
            )

            if _is_bracket_fill(stop_order):
                await self._record_fill_from_bracket(
                    user_id,
                    doc,
                    reason="stop_loss",
                    triggered_order=stop_order,
                    sibling_id=target_id,
                    api_key=api_key,
                    api_secret=api_secret,
                )
                return "closed"
            if _is_bracket_fill(target_order):
                await self._record_fill_from_bracket(
                    user_id,
                    doc,
                    reason="take_profit",
                    triggered_order=target_order,
                    sibling_id=stop_id,
                    api_key=api_key,
                    api_secret=api_secret,
                )
                return "closed"

            open_legs = await self._delta.find_bracket_legs(api_key, api_secret, symbol)
            has_open_legs = bool(open_legs.stop_loss_order_id or open_legs.take_profit_order_id)

            # Peer filled: stored sibling cancelled/missing and no open brackets remain.
            if not has_open_legs:
                if _is_bracket_cancelled(stop_order) and target_id and target_order is None:
                    await self._record_fill_from_bracket(
                        user_id,
                        doc,
                        reason="take_profit",
                        triggered_order=type(
                            "FilledBracket",
                            (),
                            {"id": int(target_id), "average_fill_price": None, "status": "CLOSED"},
                        )(),
                        sibling_id=stop_id,
                        api_key=api_key,
                        api_secret=api_secret,
                    )
                    return "closed"
                if _is_bracket_cancelled(target_order) and stop_id and stop_order is None:
                    await self._record_fill_from_bracket(
                        user_id,
                        doc,
                        reason="stop_loss",
                        triggered_order=type(
                            "FilledBracket",
                            (),
                            {"id": int(stop_id), "average_fill_price": None, "status": "CLOSED"},
                        )(),
                        sibling_id=target_id,
                        api_key=api_key,
                        api_secret=api_secret,
                    )
                    return "closed"

                known = [o for o in (stop_order, target_order) if o is not None]
                if not known or all(_is_bracket_cancelled(o) for o in known):
                    await self._clear_bracket_bookkeeping(doc)
                    return "fallback"

            if has_open_legs or any(
                _is_bracket_pending(o) for o in (stop_order, target_order) if o is not None
            ):
                return "protected"
            await self._clear_bracket_bookkeeping(doc)
            return "fallback"
        except Exception:
            log.warning(
                "ST Options: bracket reconciliation failed user=%s symbol=%s",
                user_id,
                doc.get("optionSymbol"),
                exc_info=True,
            )
            return "protected"

    async def _maybe_move_sl_to_breakeven(
        self,
        user_id: str,
        doc: dict[str, Any],
        live_premium: float,
    ) -> dict[str, Any]:
        """If decay trail triggers, move stopPremium to entry and amend broker SL when possible."""
        if doc.get("slMovedToBreakeven"):
            return doc
        entry = float(doc.get("premiumReceived") or 0)
        decay_pct = float(doc.get("breakevenDecayPct", DEFAULT_BREAKEVEN_DECAY_PCT))
        if not should_move_sl_to_breakeven(
            entry,
            live_premium,
            decay_pct=decay_pct,
            already_moved=False,
        ):
            return doc

        symbol = doc.get("optionSymbol")
        await self._trades.update_one(
            {"_id": doc["_id"], "status": STATUS_OPEN},
            {
                "$set": {
                    "stopPremium": entry,
                    "stopLossPct": 0.0,
                    "slMovedToBreakeven": True,
                    "updatedAt": _now(),
                }
            },
        )
        doc["stopPremium"] = entry
        doc["stopLossPct"] = 0.0
        doc["slMovedToBreakeven"] = True

        amended = False
        stop_order_id = doc.get("stopOrderId")
        if stop_order_id and doc.get("bracketAttached"):
            try:
                user = await self._load_user(user_id)
                account_id = str(doc.get("accountId") or user.get("selectedAccountId") or "")
                accounts = await self._accounts.list_raw_accounts(user)
                account = next(
                    (row for row in accounts if str(row.get("_id")) == account_id),
                    None,
                )
                if account is None and user.get("selectedAccountId"):
                    account = await self._selected_account(user)
                if account:
                    api_key, api_secret = self._credentials(account)
                    product = await self._delta.fetch_product(str(symbol))
                    await self._delta.amend_bracket(
                        api_key,
                        api_secret,
                        int(stop_order_id),
                        product,
                        stop_loss=entry,
                    )
                    amended = True
            except Exception:
                log.exception(
                    "ST Options: amend SL to breakeven failed user=%s symbol=%s",
                    user_id,
                    symbol,
                )

        tech = (
            f"Moved SL to breakeven user={user_id} symbol={symbol} entry={entry:.2f} "
            f"decayPct={decay_pct} live={live_premium:.2f} amended={amended}"
        )
        log.info("ST Options: %s", tech)
        self._push_activity(
            user_id,
            tech,
            user_message=(
                f"Moved stop to breakeven on {symbol} after {decay_pct:g}% premium decay"
                + ("" if amended else " (broker amend pending — soft stop active)")
            ),
            level="success" if amended else "warn",
        )
        return doc

    async def _manage_open_premiums(self, user_id: str, config: dict[str, Any] | None = None) -> None:
        if config is None:
            config = await self.get_config({"id": user_id})
        decay_pct = float(config.get("pairHedgeDecayPct") or 0)
        max_risk = float(config.get("maxRisk") or DEFAULT_MAX_RISK)
        indicator = await self._indicator_snapshot(config)
        live_st_colour = (indicator or {}).get("stColour")
        live_st_change = (indicator or {}).get("stColourChangeTime")
        cursor = self._trades.find({"userId": user_id, "status": STATUS_OPEN})
        async for doc in cursor:
            if doc.get("legRole") == "hedge":
                continue
            symbol = doc.get("optionSymbol")
            if not symbol:
                continue
            symbols = {normalize_symbol(symbol)}
            if doc.get("hedgeSymbol"):
                symbols.add(normalize_symbol(str(doc["hedgeSymbol"])))
            await self._market.ensure_symbols(symbols)

            ticker = self._market.latest_tickers.get(normalize_symbol(symbol))
            premium = _ticker_premium(ticker)
            entry = float(doc.get("premiumReceived") or 0)
            updates: dict[str, Any] = {"updatedAt": _now()}
            if premium is not None:
                updates["livePremium"] = float(premium)
                doc["livePremium"] = float(premium)
            # Keep Bias current on Running cards (also backfills adopted trades).
            if live_st_colour and doc.get("stColour") != live_st_colour:
                updates["stColour"] = live_st_colour
                doc["stColour"] = live_st_colour
                if live_st_change:
                    updates["stColourChangeTime"] = live_st_change
                    doc["stColourChangeTime"] = live_st_change
            if indicator and indicator.get("ema") is not None and doc.get("emaPrice") is None:
                updates["emaPrice"] = indicator.get("ema")
                doc["emaPrice"] = indicator.get("ema")

            if _hedge_is_open(doc) and doc.get("hedgeSymbol"):
                hedge_ticker = self._market.latest_tickers.get(
                    normalize_symbol(str(doc["hedgeSymbol"]))
                )
                hedge_live = _ticker_premium(hedge_ticker)
                if hedge_live is not None:
                    updates["hedgeLivePremium"] = float(hedge_live)
                    doc["hedgeLivePremium"] = float(hedge_live)

            if len(updates) > 1:
                await self._trades.update_one({"_id": doc["_id"]}, {"$set": updates})

            if premium is not None:
                doc = await self._maybe_move_sl_to_breakeven(user_id, doc, float(premium))

            # Open decay hedge when enabled and conditions met (hot-toggle aware).
            if (
                decay_pct > 0
                and not _hedge_is_open(doc)
                and str(doc.get("hedgeStatus") or HEDGE_STATUS_NONE)
                not in {HEDGE_STATUS_OPEN, HEDGE_STATUS_CLOSED}
                and premium is not None
                and should_open_decay_hedge(entry, float(premium), decay_pct)
            ):
                opened = await self._open_live_hedge(user_id, doc, max_risk=max_risk)
                if opened is not None:
                    doc = opened

            cv = float(
                doc.get("contractValue")
                or contract_value_for(doc.get("underlying", "BTC"))
            )
            lots = int(doc.get("lots") or 1)
            main_live = float(
                doc["livePremium"]
                if doc.get("livePremium") is not None
                else (premium if premium is not None else entry)
            )
            main_pnl = short_option_pnl(entry, main_live, cv, lots) if entry else 0.0

            # Combined open-pair max-loss flatten + frozen hedge stop.
            if _hedge_is_open(doc):
                hedge_entry = float(doc["hedgePremiumReceived"])
                hedge_live = float(
                    doc["hedgeLivePremium"]
                    if doc.get("hedgeLivePremium") is not None
                    else hedge_entry
                )
                hedge_lots = int(doc.get("hedgeLots") or lots)
                hedge_pnl = short_option_pnl(hedge_entry, hedge_live, cv, hedge_lots)
                hedge_stop = doc.get("hedgeStopPremium")
                hit_hedge_stop = (
                    hedge_stop is not None and float(hedge_live) >= float(hedge_stop)
                )
                if main_pnl + hedge_pnl <= -max_risk or hit_hedge_stop:
                    await self._close_live_trade(
                        user_id, doc, reason="max_loss", exit_premium=main_live
                    )
                    continue
                # If broker hedge SL already filled, flatten main.
                if await self._reconcile_hedge_broker_stop(user_id, doc):
                    continue
            elif entry and main_pnl <= -max_risk:
                await self._close_live_trade(
                    user_id, doc, reason="max_loss", exit_premium=main_live
                )
                continue

            bracket_state = await self._reconcile_broker_bracket(user_id, doc)
            if bracket_state == "closed":
                continue
            # Delta closed outside ST brackets (manual / liquidate / cancelled legs).
            if await self._maybe_close_if_broker_flat(user_id, doc):
                continue
            if bracket_state == "protected":
                continue
            if premium is None:
                continue
            stop_level = doc.get("stopPremium")
            reason, exit_px = evaluate_premium_brackets(
                entry_premium=entry,
                option_high=float(premium),
                option_low=float(premium),
                option_close=float(premium),
                stop_loss_pct=float(doc.get("stopLossPct", DEFAULT_STOP_LOSS_PCT)),
                take_profit_pct=float(doc.get("takeProfitPct", DEFAULT_TAKE_PROFIT_PCT)),
                stop_premium_level=float(stop_level) if stop_level is not None else None,
            )
            if reason:
                await self._close_live_trade(user_id, doc, reason=reason, exit_premium=exit_px)

    async def _load_products_for_expiry(self, coin: str, expiry: date) -> list[ProductSummary]:
        return await self._delta.fetch_products_filtered(
            underlying=coin,
            expiry_date=expiry.isoformat(),
            contract_types="call_options,put_options",
            states="live",
            max_pages=5,
        )

    async def _premium_map(
        self, coin: str, close_ts: int
    ) -> tuple[dict[tuple, float | None], dict[tuple, str]]:
        """Build (expiry, strike, side) -> premium and symbol maps for eligible expiries."""
        premium_cache: dict[tuple, float | None] = {}
        symbol_cache: dict[tuple, str] = {}
        for _, expiry in eligible_expiries(close_ts):
            products = await self._load_products_for_expiry(coin, expiry)
            symbols = {p.symbol for p in products if p.symbol}
            if symbols:
                await self._market.ensure_symbols(symbols)
            for product in products:
                if product.strike_price is None:
                    continue
                if not product_matches_expiry(product, expiry):
                    continue
                side = _product_side(product)
                key = (expiry, float(product.strike_price), side)
                symbol_cache[key] = product.symbol
                prem = None
                ticker = self._market.latest_tickers.get(normalize_symbol(product.symbol))
                if ticker and (ticker.mark_price or ticker.last_price):
                    prem = float(ticker.mark_price or ticker.last_price)
                else:
                    try:
                        inst = await self._delta.fetch_ticker(product.symbol)
                        if inst.mark_price:
                            prem = float(inst.mark_price)
                        elif inst.close_price:
                            prem = float(inst.close_price)
                    except Exception:
                        prem = None
                premium_cache[key] = prem
                constructed = delta_option_symbol(side, coin, float(product.strike_price), expiry)  # type: ignore[arg-type]
                premium_cache[(constructed, expiry, float(product.strike_price), side)] = prem
        return premium_cache, symbol_cache

    async def _option_ticker_volumes(self, coin: str) -> dict[str, float]:
        """Map option symbol → Delta ticker volume (missing/invalid → omitted, treated as 0)."""
        out: dict[str, float] = {}
        try:
            rows = await self._delta.fetch_tickers(
                underlying=coin,
                contract_types="call_options,put_options",
            )
        except Exception:
            log.exception("ST Options: ticker volume fetch failed underlying=%s", coin)
            return out
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            symbol = normalize_symbol(str(row.get("symbol") or ""))
            if not symbol:
                continue
            raw = row.get("volume")
            try:
                out[symbol] = max(0.0, float(raw or 0))
            except (TypeError, ValueError):
                out[symbol] = 0.0
        return out

    async def _discover_bracket_legs(
        self,
        api_key: str,
        api_secret: str,
        symbol: str,
        *,
        attempts: int = 3,
    ) -> Any:
        legs = None
        for attempt in range(max(1, attempts)):
            legs = await self._delta.find_bracket_legs(api_key, api_secret, symbol)
            if legs.stop_loss_order_id and legs.take_profit_order_id:
                return legs
            if attempt < attempts - 1:
                await asyncio.sleep(0.25 * (attempt + 1))
        return legs

    async def _persist_discovered_brackets(
        self,
        user_id: str,
        doc: dict[str, Any],
        legs: Any,
        api_key: str,
        api_secret: str,
        *,
        adopted_existing: bool = False,
    ) -> bool:
        stop_id = legs.stop_loss_order_id
        target_id = legs.take_profit_order_id
        if not stop_id or not target_id:
            return False
        fields: dict[str, Any] = {
            "stopOrderId": stop_id,
            "takeProfitOrderId": target_id,
            "bracketAttached": True,
            "updatedAt": _now(),
        }
        # Prefer broker stop/target prices when linking legs the user (or Delta) already set.
        stop_order = None
        target_order = None
        with contextlib.suppress(Exception):
            stop_order = await self._delta.fetch_order(api_key, api_secret, int(stop_id))
            stop_px = getattr(stop_order, "stop_price", None) if stop_order else None
            if stop_px is not None and float(stop_px) > 0:
                fields["stopPremium"] = float(stop_px)
                doc["stopPremium"] = float(stop_px)
        with contextlib.suppress(Exception):
            target_order = await self._delta.fetch_order(api_key, api_secret, int(target_id))
            target_px = getattr(target_order, "stop_price", None) if target_order else None
            if target_px is not None and float(target_px) > 0:
                fields["targetPremium"] = float(target_px)
                doc["targetPremium"] = float(target_px)
        log.info(
            "ST Options: SL leg user=%s symbol=%s orderType=%s limitPrice=%s stopPrice=%s",
            user_id,
            doc.get("optionSymbol"),
            getattr(stop_order, "order_type", None) if stop_order else None,
            getattr(stop_order, "limit_price", None) if stop_order else None,
            getattr(stop_order, "stop_price", None) if stop_order else None,
        )
        doc["stopOrderId"] = stop_id
        doc["takeProfitOrderId"] = target_id
        doc["bracketAttached"] = True
        await self._trades.update_one(
            {"_id": doc["_id"], "status": STATUS_OPEN},
            {"$set": fields, "$unset": {"bracketError": ""}},
        )
        symbol = str(doc.get("optionSymbol") or "")
        if adopted_existing:
            tech = (
                f"Linked existing broker SL/TP user={user_id} symbol={symbol} "
                f"stopId={stop_id} targetId={target_id}"
            )
            log.info("ST Options: %s", tech)
            self._push_activity(
                user_id,
                tech,
                user_message=f"Linked existing stop/target on {symbol}",
                level="success",
            )
        return True

    async def _attach_bracket_protection(
        self,
        user_id: str,
        doc: dict[str, Any],
        product: ProductSummary,
        api_key: str,
        api_secret: str,
    ) -> bool:
        symbol = str(doc.get("optionSymbol") or product.symbol)
        stop_level = float(doc["stopPremium"])
        target_level = float(doc["targetPremium"])
        bracket_placed = False

        # Already protected on Delta (e.g. manual SL/TP) — link IDs, do not place again.
        existing = await self._discover_bracket_legs(api_key, api_secret, symbol, attempts=2)
        if (
            existing
            and existing.stop_loss_order_id
            and existing.take_profit_order_id
        ):
            return await self._persist_discovered_brackets(
                user_id,
                doc,
                existing,
                api_key,
                api_secret,
                adopted_existing=True,
            )

        try:
            await self._delta.place_position_bracket(
                api_key,
                api_secret,
                product,
                stop_level,
                target_level,
            )
            bracket_placed = True
            legs = await self._discover_bracket_legs(api_key, api_secret, symbol, attempts=3)
            if not legs or not legs.stop_loss_order_id or not legs.take_profit_order_id:
                raise RuntimeError("Delta bracket legs were not discoverable after placement")
            return await self._persist_discovered_brackets(
                user_id, doc, legs, api_key, api_secret, adopted_existing=False
            )
        except Exception as exc:
            # Place often fails when a bracket already exists — adopt whatever is on the book.
            recovered = await self._discover_bracket_legs(api_key, api_secret, symbol, attempts=3)
            if (
                recovered
                and recovered.stop_loss_order_id
                and recovered.take_profit_order_id
            ):
                return await self._persist_discovered_brackets(
                    user_id,
                    doc,
                    recovered,
                    api_key,
                    api_secret,
                    adopted_existing=True,
                )
            fallback = not bracket_placed
            tech = (
                f"Bracket {'attach' if fallback else 'discovery'} failed user={user_id} "
                f"symbol={symbol} stop={stop_level:.2f} target={target_level:.2f}; "
                f"{'soft monitoring active' if fallback else 'broker bracket will be reconciled'}"
            )
            log.exception("ST Options: %s", tech)
            doc["bracketAttached"] = bracket_placed
            await self._trades.update_one(
                {"_id": doc["_id"], "status": STATUS_OPEN},
                {
                    "$set": {
                        "bracketAttached": bracket_placed,
                        "bracketError": str(exc),
                        "updatedAt": _now(),
                    }
                },
            )
            self._push_activity(
                user_id,
                tech,
                user_message=(
                    f"Broker protection could not be attached to {symbol}; monitoring it here"
                    if fallback
                    else f"Broker protection attached to {symbol}; confirming order details"
                ),
                level="warn",
            )
            return bracket_placed

    async def _find_short_option_position(
        self,
        api_key: str,
        api_secret: str,
        symbol: str,
    ) -> tuple[float, float | None] | None:
        """Return (lots, entry_premium) if a short position exists on symbol."""
        want = normalize_symbol(symbol)
        try:
            positions = await self._delta.fetch_margined_positions(api_key, api_secret)
        except Exception:
            log.exception("ST Options: failed to fetch positions while confirming fill symbol=%s", want)
            return None
        for raw in positions or []:
            if not isinstance(raw, dict):
                continue
            pos_symbol = normalize_symbol(str(raw.get("product_symbol") or raw.get("symbol") or ""))
            if pos_symbol != want:
                continue
            parsed = _short_position_lots_and_entry(raw)
            if parsed is not None:
                return parsed
        return None

    async def _lookup_entry_sell_fill(
        self,
        api_key: str,
        api_secret: str,
        symbol: str,
        *,
        order_id: int | None = None,
    ) -> tuple[float, float] | None:
        """Return (lots, fill_price) for a recent sell fill on symbol (optional order_id match)."""
        want = normalize_symbol(symbol)
        try:
            fills = await self._delta.fetch_fills(api_key, api_secret, page_size=50)
        except Exception:
            log.exception("ST Options: fetch_fills failed while confirming entry symbol=%s", want)
            return None
        for fill in fills or []:
            if not isinstance(fill, dict):
                continue
            pos_symbol = normalize_symbol(
                str(fill.get("product_symbol") or fill.get("symbol") or "")
            )
            if pos_symbol != want:
                continue
            side = str(fill.get("side") or "").lower()
            if side not in {"sell", "ask"}:
                continue
            if order_id is not None:
                fill_oid = fill.get("order_id") or fill.get("orderId")
                try:
                    if fill_oid is not None and int(fill_oid) != int(order_id):
                        continue
                except (TypeError, ValueError):
                    pass
            raw_px = (
                fill.get("price")
                or fill.get("fill_price")
                or fill.get("average_fill_price")
            )
            raw_size = fill.get("size") or fill.get("fill_size") or fill.get("quantity")
            try:
                price = float(raw_px) if raw_px is not None else None
            except (TypeError, ValueError):
                price = None
            try:
                lots = float(raw_size) if raw_size is not None else None
            except (TypeError, ValueError):
                lots = None
            if price is None or price <= 0:
                continue
            if lots is None or lots <= 0:
                lots = 1.0
            return abs(lots), price
        return None

    def _synthetic_filled_order(
        self,
        order: Any,
        *,
        product_symbol: str,
        lots: float,
        fill_px: float,
    ) -> OrderSummary:
        return OrderSummary(
            id=int(getattr(order, "id", 0) or 0),
            symbol=normalize_symbol(product_symbol),
            product_id=int(getattr(order, "product_id", 0) or 0),
            order_type=str(getattr(order, "order_type", "") or "limit_order"),
            side=str(getattr(order, "side", "SELL") or "SELL"),
            limit_price=getattr(order, "limit_price", None),
            stop_price=None,
            take_profit_price=None,
            stop_loss_price=None,
            size=float(lots),
            unfilled_size=0.0,
            status="CLOSED",
            created_at=str(getattr(order, "created_at", "") or ""),
            average_fill_price=float(fill_px) if fill_px else None,
        )

    async def _force_cancel_working_entry(
        self,
        api_key: str,
        api_secret: str,
        order: Any,
        *,
        product: ProductSummary | None = None,
        product_symbol: str | None = None,
    ) -> Any:
        """Retry cancel until the entry is cancelled, filled, or gone. 404 is not success."""
        order_id = int(getattr(order, "id", 0) or 0)
        if order_id <= 0:
            return order
        prod = product
        if prod is None and product_symbol:
            with contextlib.suppress(Exception):
                prod = await self._delta.fetch_product(product_symbol)
        for attempt in range(ENTRY_CANCEL_RETRIES):
            refreshed = await self._delta.fetch_order(api_key, api_secret, order_id)
            if refreshed is not None:
                order = refreshed
                if _is_limit_entry_filled(order):
                    return order
                status = _order_status(order)
                if status in _BRACKET_CANCEL_STATUSES and _order_filled_size(order) <= 0:
                    return order
                if not is_open_order_status(status):
                    return order
            try:
                await self._delta.cancel_order(api_key, api_secret, order_id)
            except Exception as exc:
                log.warning(
                    "ST Options: entry cancel retry orderId=%s attempt=%s err=%s",
                    order_id,
                    attempt + 1,
                    exc,
                )
            if prod is not None:
                with contextlib.suppress(Exception):
                    await self._delta.cancel_all_entry_orders(api_key, api_secret, prod)
            if attempt < ENTRY_CANCEL_RETRIES - 1:
                await asyncio.sleep(0.2 * (attempt + 1))
        refreshed = await self._delta.fetch_order(api_key, api_secret, order_id)
        return refreshed if refreshed is not None else order

    async def _await_limit_fill_or_cancel(
        self,
        api_key: str,
        api_secret: str,
        order: Any,
        *,
        product: ProductSummary | None = None,
        product_symbol: str | None = None,
        fallback_limit: float | None = None,
        poll_attempts: int = 8,
    ) -> Any | None:
        """Wait for a limit fill; on timeout cancel, then re-check order + fills + position.

        Never returns None while a short position or sell fill exists on ``product_symbol`` —
        that would leave an unprotected broker position.
        """
        if _is_limit_entry_filled(order):
            return order
        for attempt in range(poll_attempts):
            refreshed = await self._delta.fetch_order(api_key, api_secret, int(order.id))
            if refreshed is not None:
                order = refreshed
                if _is_limit_entry_filled(order):
                    return order
            if attempt < poll_attempts - 1:
                await asyncio.sleep(0.25 * (attempt + 1))

        order = await self._force_cancel_working_entry(
            api_key,
            api_secret,
            order,
            product=product,
            product_symbol=product_symbol,
        )
        if _is_limit_entry_filled(order):
            return order
        status = _order_status(order)
        cancel_suspect = is_open_order_status(status)

        # Cancel may race a fill — always re-fetch before declaring unfilled.
        for attempt in range(5):
            refreshed = await self._delta.fetch_order(api_key, api_secret, int(order.id))
            if refreshed is not None:
                order = refreshed
                if _is_limit_entry_filled(order):
                    return order
                status = _order_status(order)
                if (
                    status in _BRACKET_CANCEL_STATUSES
                    and _order_filled_size(order) <= 0
                    and getattr(order, "average_fill_price", None) in (None, 0, 0.0)
                ):
                    break
            if attempt < 4:
                await asyncio.sleep(0.2)

        if _is_limit_entry_filled(order):
            return order

        if product_symbol:
            sell_fill = await self._lookup_entry_sell_fill(
                api_key,
                api_secret,
                product_symbol,
                order_id=int(getattr(order, "id", 0) or 0) or None,
            )
            if sell_fill is None:
                sell_fill = await self._lookup_entry_sell_fill(
                    api_key, api_secret, product_symbol, order_id=None
                )
            if sell_fill is not None:
                lots, fill_px = sell_fill
                log.warning(
                    "ST Options: recovered fill from sells API symbol=%s lots=%s "
                    "entry=%s orderId=%s cancelSuspect=%s",
                    product_symbol,
                    lots,
                    fill_px,
                    getattr(order, "id", None),
                    cancel_suspect,
                )
                return self._synthetic_filled_order(
                    order, product_symbol=product_symbol, lots=lots, fill_px=fill_px
                )

            # Positions can lag after a fill — poll with backoff.
            attempts = POSITION_RECOVERY_ATTEMPTS if cancel_suspect else max(4, POSITION_RECOVERY_ATTEMPTS // 2)
            for attempt in range(attempts):
                pos = await self._find_short_option_position(api_key, api_secret, product_symbol)
                if pos is not None:
                    lots, entry = pos
                    fill_px = entry or fallback_limit or getattr(order, "limit_price", None) or 0.0
                    log.warning(
                        "ST Options: recovered fill from open short position symbol=%s lots=%s "
                        "entry=%s orderId=%s attempt=%s cancelSuspect=%s",
                        product_symbol,
                        lots,
                        fill_px,
                        getattr(order, "id", None),
                        attempt + 1,
                        cancel_suspect,
                    )
                    return self._synthetic_filled_order(
                        order,
                        product_symbol=product_symbol,
                        lots=lots,
                        fill_px=float(fill_px) if fill_px else 0.0,
                    )
                if attempt < attempts - 1:
                    await asyncio.sleep(0.35 * (attempt + 1))

        log.warning(
            "ST Options: limit still unfilled after cancel/recover %s symbol=%s "
            "cancelSuspect=%s fallbackLimit=%s",
            _order_fill_debug(order),
            product_symbol,
            cancel_suspect,
            fallback_limit,
        )
        return None

    async def _promote_pending_entry(
        self,
        user_id: str,
        doc: dict[str, Any],
        *,
        fill: float,
        lots: float,
        product: ProductSummary,
        api_key: str,
        api_secret: str,
        recovered_from_position: bool = False,
    ) -> dict[str, Any]:
        """Promote pending_entry → open and attach broker SL/TP immediately."""
        stop_loss_pct = float(doc.get("stopLossPct") or DEFAULT_STOP_LOSS_PCT)
        take_profit_pct = float(doc.get("takeProfitPct") or DEFAULT_TAKE_PROFIT_PCT)
        stop_level = stop_premium(fill, stop_loss_pct)
        target_level = target_premium(fill, take_profit_pct)
        lots_n = normalize_order_size(float(lots))
        now = _now()
        fields = {
            "status": STATUS_OPEN,
            "premiumReceived": fill,
            "livePremium": fill,
            "stopPremium": stop_level,
            "targetPremium": target_level,
            "lots": lots_n,
            "bracketAttached": False,
            "updatedAt": now,
        }
        await self._trades.update_one({"_id": doc["_id"]}, {"$set": fields})
        doc.update(fields)
        await self._attach_bracket_protection(
            user_id,
            doc,
            product,
            api_key,
            api_secret,
        )
        symbol = str(doc.get("optionSymbol") or "")
        tech = (
            f"{'Recovered' if recovered_from_position else 'Opened'} user={user_id} "
            f"symbol={symbol} fill={fill:.2f} lots={lots_n} stop={stop_level:.2f} "
            f"target={target_level:.2f} bracket={doc.get('bracketAttached')} "
            f"orderId={doc.get('entryOrderId')}"
        )
        log.info("ST Options: %s", tech)
        self._push_activity(
            user_id,
            tech,
            user_message=(
                f"Recovered untracked fill on {symbol} — attaching stop/target"
                if recovered_from_position
                else f"Opened a trade ({symbol})"
            ),
            level="warn" if recovered_from_position or not doc.get("bracketAttached") else "success",
        )
        return doc

    async def _reconcile_pending_entries(self, user_id: str, config: dict[str, Any]) -> None:
        """Adopt pending entries that filled (or have a short position) and attach SL/TP."""
        cursor = self._trades.find({"userId": user_id, "status": STATUS_PENDING_ENTRY})
        async for doc in cursor:
            symbol = str(doc.get("optionSymbol") or "")
            if not symbol:
                continue
            try:
                api_key, api_secret = await self._trade_credentials(user_id, doc)
            except Exception:
                log.exception("ST Options: pending entry credentials failed user=%s", user_id)
                continue
            order_id = doc.get("entryOrderId")
            order = None
            if order_id:
                order = await self._delta.fetch_order(api_key, api_secret, int(order_id))
            limit_price = float(doc.get("entryLimitPrice") or doc.get("premiumReceived") or 0)
            filled = order if _is_limit_entry_filled(order) else None
            recovered = False
            if filled is None:
                pos = await self._find_short_option_position(api_key, api_secret, symbol)
                if pos is not None:
                    lots, entry = pos
                    fill = float(entry or limit_price)
                    recovered = True
                    try:
                        product = await self._delta.fetch_product(symbol)
                    except Exception:
                        log.exception(
                            "ST Options: pending recover product missing user=%s symbol=%s",
                            user_id,
                            symbol,
                        )
                        continue
                    await self._promote_pending_entry(
                        user_id,
                        doc,
                        fill=fill,
                        lots=lots,
                        product=product,
                        api_key=api_key,
                        api_secret=api_secret,
                        recovered_from_position=True,
                    )
                    continue
                sell_fill = await self._lookup_entry_sell_fill(
                    api_key,
                    api_secret,
                    symbol,
                    order_id=int(order_id) if order_id else None,
                )
                if sell_fill is not None:
                    lots, fill_px = sell_fill
                    try:
                        product = await self._delta.fetch_product(symbol)
                    except Exception:
                        log.exception(
                            "ST Options: pending sell-fill product missing user=%s symbol=%s",
                            user_id,
                            symbol,
                        )
                        continue
                    await self._promote_pending_entry(
                        user_id,
                        doc,
                        fill=float(fill_px or limit_price),
                        lots=lots,
                        product=product,
                        api_key=api_key,
                        api_secret=api_secret,
                        recovered_from_position=True,
                    )
                    continue
                status = _order_status(order)
                skip_min_age = False
                if order is not None and is_open_order_status(status):
                    order = await self._force_cancel_working_entry(
                        api_key,
                        api_secret,
                        order,
                        product_symbol=symbol,
                    )
                    skip_min_age = True
                    if _is_limit_entry_filled(order):
                        filled = order
                    else:
                        pos = await self._find_short_option_position(api_key, api_secret, symbol)
                        if pos is not None:
                            lots, entry = pos
                            try:
                                product = await self._delta.fetch_product(symbol)
                            except Exception:
                                continue
                            await self._promote_pending_entry(
                                user_id,
                                doc,
                                fill=float(entry or limit_price),
                                lots=lots,
                                product=product,
                                api_key=api_key,
                                api_secret=api_secret,
                                recovered_from_position=True,
                            )
                            continue
                    status = _order_status(order)
                elif order is not None and status in _BRACKET_CANCEL_STATUSES:
                    skip_min_age = True
                if filled is None and order is not None and status not in _BRACKET_CANCEL_STATUSES:
                    with contextlib.suppress(Exception):
                        await self._delta.cancel_order(api_key, api_secret, int(order_id))
                    pos = await self._find_short_option_position(api_key, api_secret, symbol)
                    if pos is not None:
                        lots, entry = pos
                        try:
                            product = await self._delta.fetch_product(symbol)
                        except Exception:
                            continue
                        await self._promote_pending_entry(
                            user_id,
                            doc,
                            fill=float(entry or limit_price),
                            lots=lots,
                            product=product,
                            api_key=api_key,
                            api_secret=api_secret,
                            recovered_from_position=True,
                        )
                        continue

                if filled is not None:
                    fill = float(getattr(filled, "average_fill_price", None) or limit_price)
                    filled_lots = _order_filled_size(filled) or float(doc.get("lots") or 1)
                    try:
                        product = await self._delta.fetch_product(symbol)
                    except Exception:
                        continue
                    await self._promote_pending_entry(
                        user_id,
                        doc,
                        fill=fill,
                        lots=filled_lots,
                        product=product,
                        api_key=api_key,
                        api_secret=api_secret,
                        recovered_from_position=False,
                    )
                    continue

                # Patient clear — never drop on the first empty check (positions/fills lag).
                created = doc.get("createdAt")
                age_s = 0.0
                if isinstance(created, datetime):
                    age_s = max(0.0, (_now() - created).total_seconds())
                confirm = int(doc.get("unfilledConfirmCount") or 0) + 1
                await self._trades.update_one(
                    {"_id": doc["_id"], "status": STATUS_PENDING_ENTRY},
                    {"$set": {"unfilledConfirmCount": confirm, "updatedAt": _now()}},
                )
                wait_age = (not skip_min_age) and age_s < PENDING_MIN_AGE_SECONDS
                if confirm < PENDING_UNFILLED_CONFIRM_TICKS or wait_age:
                    log.info(
                        "ST Options: pending unfilled confirm user=%s symbol=%s "
                        "count=%s age=%.0fs order=%s skipMinAge=%s",
                        user_id,
                        symbol,
                        confirm,
                        age_s,
                        _order_fill_debug(order),
                        skip_min_age,
                    )
                    continue
                await self._trades.delete_one({"_id": doc["_id"], "status": STATUS_PENDING_ENTRY})
                tech = (
                    f"Cleared pending entry user={user_id} symbol={symbol} "
                    f"orderId={order_id} (no fill, no position after {confirm} confirms)"
                )
                log.info("ST Options: %s", tech)
                self._push_activity(
                    user_id,
                    tech,
                    user_message=f"Setup skipped — limit entry did not fill ({symbol})",
                    level="warn",
                )
                continue

            fill = float(
                getattr(filled, "average_fill_price", None) or limit_price
            )
            filled_lots = _order_filled_size(filled) or float(doc.get("lots") or 1)
            try:
                product = await self._delta.fetch_product(symbol)
            except Exception:
                log.exception(
                    "ST Options: pending fill product missing user=%s symbol=%s",
                    user_id,
                    symbol,
                )
                continue
            await self._promote_pending_entry(
                user_id,
                doc,
                fill=fill,
                lots=filled_lots,
                product=product,
                api_key=api_key,
                api_secret=api_secret,
                recovered_from_position=recovered,
            )

    async def _sync_broker_shorts_with_st(self, user_id: str, config: dict[str, Any]) -> None:
        """Adopt naked short options into ST trades and attach missing SL/TP brackets."""
        coin = normalize_underlying(str(config.get("underlying") or "BTC"))
        try:
            user = await self._load_user(user_id)
            account = await self._selected_account(user)
            api_key, api_secret = self._credentials(account)
        except Exception:
            log.exception("ST Options: orphan sync credentials failed user=%s", user_id)
            return

        claimed: set[str] = set()
        cursor = self._trades.find(
            {"userId": user_id, "status": {"$in": [STATUS_OPEN, STATUS_PENDING_ENTRY]}}
        )
        async for doc in cursor:
            main_sym = normalize_symbol(str(doc.get("optionSymbol") or ""))
            if main_sym:
                claimed.add(main_sym)
            if _hedge_is_open(doc):
                hedge_sym = normalize_symbol(str(doc.get("hedgeSymbol") or ""))
                if hedge_sym:
                    claimed.add(hedge_sym)

        # Retry brackets on tracked opens that are still unprotected.
        open_docs = await self._list_trade_docs(user_id, status=STATUS_OPEN)
        for doc in open_docs:
            if (
                doc.get("bracketAttached")
                and doc.get("stopOrderId")
                and doc.get("takeProfitOrderId")
            ):
                continue
            symbol = str(doc.get("optionSymbol") or "")
            if not symbol:
                continue
            try:
                creds = await self._trade_credentials(user_id, doc)
                product = await self._delta.fetch_product(symbol)
                await self._attach_bracket_protection(
                    user_id, doc, product, creds[0], creds[1]
                )
            except Exception:
                log.exception(
                    "ST Options: bracket retry failed user=%s symbol=%s",
                    user_id,
                    symbol,
                )

        try:
            positions = await self._delta.fetch_margined_positions(api_key, api_secret)
        except Exception:
            log.exception("ST Options: orphan sync positions failed user=%s", user_id)
            return

        stop_loss_pct = float(config.get("stopLossPct") or DEFAULT_STOP_LOSS_PCT)
        take_profit_pct = float(config.get("takeProfitPct") or DEFAULT_TAKE_PROFIT_PCT)
        breakeven_decay_pct = float(
            config.get("breakevenDecayPct")
            if config.get("breakevenDecayPct") is not None
            else DEFAULT_BREAKEVEN_DECAY_PCT
        )
        now = _now()
        now_ts = int(now.timestamp())

        for raw in positions or []:
            if not isinstance(raw, dict):
                continue
            symbol = normalize_symbol(
                str(raw.get("product_symbol") or raw.get("symbol") or "")
            )
            if not symbol.startswith(("C-", "P-")):
                continue
            if f"-{coin}-" not in symbol:
                continue
            parsed = _short_position_lots_and_entry(raw)
            if parsed is None:
                continue
            if symbol in claimed:
                continue

            lots, entry = parsed
            fill = float(entry) if entry and entry > 0 else 0.0
            if fill <= 0:
                mark = raw.get("mark_price") or raw.get("markPrice")
                try:
                    fill = float(mark) if mark is not None else 0.0
                except (TypeError, ValueError):
                    fill = 0.0
            if fill <= 0:
                log.warning(
                    "ST Options: orphan short skip no entry/mark user=%s symbol=%s",
                    user_id,
                    symbol,
                )
                continue

            parts = symbol.split("-")
            try:
                strike = float(parts[2]) if len(parts) >= 4 else 0.0
            except (TypeError, ValueError):
                strike = 0.0
            expiry_day = parse_option_symbol_expiry(symbol)
            option_side = "CALL" if symbol.startswith("C-") else "PUT"
            direction = "SHORT" if option_side == "CALL" else "LONG"
            stop_level = stop_premium(fill, stop_loss_pct)
            target_level = target_premium(fill, take_profit_pct)
            cv = contract_value_for(coin)
            lots_n = normalize_order_size(float(lots))

            try:
                product = await self._delta.fetch_product(symbol)
                if product.contract_value:
                    cv = float(product.contract_value)
            except Exception:
                log.exception(
                    "ST Options: orphan adopt product missing user=%s symbol=%s",
                    user_id,
                    symbol,
                )
                continue

            indicator = await self._indicator_snapshot(config)
            doc: dict[str, Any] = {
                "userId": user_id,
                "accountId": str(account["_id"]),
                "direction": direction,
                "status": STATUS_OPEN,
                "underlying": coin,
                "date": format_ist(now_ts),
                "stColour": (indicator or {}).get("stColour"),
                "stColourChangeTime": (indicator or {}).get("stColourChangeTime"),
                "emaPrice": (indicator or {}).get("ema"),
                "strike": strike,
                "expiryDate": expiry_day.isoformat() if expiry_day else None,
                "optionSymbol": symbol,
                "optionSide": option_side,
                "legRole": "main",
                "hedgeStatus": HEDGE_STATUS_NONE,
                "hedgePending": False,
                "premiumReceived": fill,
                "livePremium": fill,
                "stopPremium": stop_level,
                "targetPremium": target_level,
                "stopLossPct": stop_loss_pct,
                "takeProfitPct": take_profit_pct,
                "breakevenDecayPct": breakeven_decay_pct,
                "slMovedToBreakeven": False,
                "stopOrderId": None,
                "takeProfitOrderId": None,
                "bracketAttached": False,
                "lots": lots_n,
                "contractValue": cv,
                "entryOrderId": None,
                "entryLimitPrice": fill,
                "entryTime": now_ts,
                "adoptedFromBroker": True,
                "createdAt": now,
                "updatedAt": now,
            }
            inserted = await self._trades.insert_one(doc)
            doc["_id"] = inserted.inserted_id
            claimed.add(symbol)
            tech = (
                f"Adopted unprotected short user={user_id} symbol={symbol} "
                f"lots={lots_n} fill={fill:.2f} — attaching stop/target"
            )
            log.warning("ST Options: %s", tech)
            self._push_activity(
                user_id,
                tech,
                user_message=f"Adopted unprotected short {symbol} — attaching stop/target",
                level="warn",
            )
            await self._attach_bracket_protection(
                user_id, doc, product, api_key, api_secret
            )

    async def _open_live_trade(
        self,
        user_id: str,
        config: dict[str, Any],
        bar: IndicatorBar,
        direction: Direction,
    ) -> None:
        signal = build_entry_signal(bar, direction)
        if signal is None:
            return
        coin = normalize_underlying(config["underlying"])
        close_ts = bar_close_unix(bar.time)
        premium_cache, symbol_cache = await self._premium_map(coin, close_ts)

        def lookup(symbol: str, expiry: date, strike: float, side: str) -> float | None:
            if (symbol, expiry, strike, side) in premium_cache:
                return premium_cache[(symbol, expiry, strike, side)]
            return premium_cache.get((expiry, float(strike), side))

        candidates = collect_option_waterfall(
            underlying=coin,
            direction=direction,
            perp_price=bar.close,
            bar_close_unix=close_ts,
            min_premium_pct=float(config["minPremiumPct"]),
            premium_lookup=lookup,
            depth=LIVE_STRIKE_DEPTH,
        )
        if not candidates:
            tech = (
                f"Skip entry user={user_id} direction={direction} reason=no_premium_or_contract "
                f"perp={bar.close} minPremiumPct={config['minPremiumPct']}"
            )
            log.info("ST Options: %s", tech)
            self._push_activity(
                user_id,
                tech,
                user_message="Setup skipped — no suitable option price found",
                level="warn",
            )
            return

        volumes = await self._option_ticker_volumes(coin)
        liquid = pick_above_average_volume(candidates, volumes)
        if not liquid:
            tech = (
                f"Skip entry user={user_id} direction={direction} reason=no_liquid_strike "
                f"band={len(candidates)} atmDepth={LIVE_STRIKE_DEPTH}"
            )
            log.info("ST Options: %s", tech)
            self._push_activity(
                user_id,
                tech,
                user_message="Setup skipped — no liquid strike (ATM±1).",
                level="warn",
            )
            return
        liquid.sort(key=lambda c: (-c.moneyness_steps, -c.expiry_offset))
        resolved = liquid[0]

        allowed = {exp for _, exp in eligible_expiries(close_ts)}
        if resolved.expiry not in allowed:
            tech = (
                f"Skip entry user={user_id} direction={direction} reason=not_t0_t1 "
                f"expiry={resolved.expiry}"
            )
            log.warning("ST Options: %s", tech)
            self._push_activity(
                user_id,
                tech,
                user_message="Setup skipped — contract day was not eligible",
                level="warn",
            )
            return

        cached = symbol_cache.get((resolved.expiry, float(resolved.strike), resolved.option_side))
        prod_symbol = resolved.symbol
        if cached and cached != resolved.symbol:
            log.warning(
                "ST Options: cache symbol %s mismatches resolved %s — using resolved",
                cached,
                resolved.symbol,
            )
        elif cached == resolved.symbol:
            prod_symbol = cached

        symbol_expiry = parse_option_symbol_expiry(prod_symbol)
        if symbol_expiry is None or symbol_expiry not in allowed:
            tech = (
                f"Skip entry user={user_id} direction={direction} reason=not_t0_t1 "
                f"symbol={prod_symbol}"
            )
            log.warning("ST Options: %s", tech)
            self._push_activity(
                user_id,
                tech,
                user_message="Setup skipped — contract day was not eligible",
                level="warn",
            )
            return

        cv = resolved.contract_value or contract_value_for(coin)
        stop_loss_pct = float(config.get("stopLossPct", DEFAULT_STOP_LOSS_PCT))
        max_risk = float(config.get("maxRisk", DEFAULT_MAX_RISK) or DEFAULT_MAX_RISK)

        user = await self._load_user(user_id)
        account = await self._selected_account(user)
        try:
            product = await self._delta.fetch_product(prod_symbol)
        except Exception:
            tech = f"Skip entry user={user_id} direction={direction} reason=product_missing symbol={prod_symbol}"
            log.exception("ST Options: %s", tech)
            self._push_activity(
                user_id,
                tech,
                user_message="Setup skipped — contract not available",
                level="warn",
            )
            return

        await self._market.ensure_symbols({prod_symbol, perp_symbol(coin)})
        live_px: float | None = None
        ticker = self._market.latest_tickers.get(normalize_symbol(prod_symbol))
        if ticker:
            live_px = ticker.mark_price or ticker.last_price
        if live_px is None:
            try:
                inst = await self._delta.fetch_ticker(prod_symbol)
                live_px = inst.mark_price or inst.close_price or inst.best_bid or inst.best_ask
            except Exception:
                log.exception(
                    "ST Options: failed to fetch ticker for limit entry symbol=%s", prod_symbol
                )
        if live_px is None or float(live_px) <= 0:
            tech = (
                f"Skip entry user={user_id} direction={direction} reason=no_live_premium "
                f"symbol={prod_symbol}"
            )
            log.warning("ST Options: %s", tech)
            self._push_activity(
                user_id,
                tech,
                user_message="Setup skipped — no live option price for limit entry",
                level="warn",
            )
            return

        limit_price = entry_limit_price(float(live_px))
        if limit_price is None:
            tech = (
                f"Skip entry user={user_id} direction={direction} reason=invalid_limit "
                f"symbol={prod_symbol} live={float(live_px):.2f}"
            )
            log.warning("ST Options: %s", tech)
            self._push_activity(
                user_id,
                tech,
                user_message="Setup skipped — limit price invalid",
                level="warn",
            )
            return

        lots = lots_from_max_risk_or_none(
            max_risk,
            limit_price,
            stop_loss_pct,
            cv,
            slippage_buffer_pct=LIVE_SL_SLIPPAGE_BUFFER_PCT,
        )
        if lots is None:
            tech = (
                f"Skip entry user={user_id} direction={direction} reason=max_risk_too_low "
                f"symbol={prod_symbol} limit={limit_price:.2f} maxRisk={max_risk} "
                f"stopLossPct={stop_loss_pct}"
            )
            log.info("ST Options: %s", tech)
            self._push_activity(
                user_id,
                tech,
                user_message="Setup skipped — one lot would exceed max risk",
                level="warn",
            )
            return

        api_key, api_secret = self._credentials(account)
        try:
            order = await self._delta.place_limit_entry(
                api_key,
                api_secret,
                product,
                "sell",
                normalize_order_size(float(lots)),
                limit_price,
            )
        except Exception as exc:
            tech = (
                f"Skip entry user={user_id} direction={direction} reason=order_failed "
                f"symbol={prod_symbol} limit={limit_price:.2f} lots={lots} "
                f"delta={_extract_delta_error_payload(exc).get('code') or type(exc).__name__}"
            )
            log.exception("ST Options: %s", tech)
            self._push_activity(
                user_id,
                tech,
                user_message=_order_failure_user_message(exc, kind="setup"),
                level="warn",
            )
            return

        # Persist immediately so a crash / mis-detect still reconciles + attaches SL/TP.
        take_profit_pct = float(config.get("takeProfitPct", DEFAULT_TAKE_PROFIT_PCT))
        breakeven_decay_pct = float(config.get("breakevenDecayPct", DEFAULT_BREAKEVEN_DECAY_PCT))
        provisional_stop = stop_premium(limit_price, stop_loss_pct)
        provisional_target = target_premium(limit_price, take_profit_pct)
        pending_doc: dict[str, Any] = {
            "userId": user_id,
            "accountId": str(account["_id"]),
            "direction": direction,
            "status": STATUS_PENDING_ENTRY,
            "underlying": coin,
            "date": format_ist(bar.time),
            "stColour": signal.st_colour,
            "stColourChangeTime": format_ist(signal.st_colour_change_time),
            "emaPrice": signal.ema,
            "strike": resolved.strike,
            "expiryDate": resolved.expiry.isoformat(),
            "optionSymbol": prod_symbol,
            "optionSide": resolved.option_side,
            "legRole": "main",
            "hedgeStatus": HEDGE_STATUS_NONE,
            "hedgePending": False,
            "premiumReceived": limit_price,
            "livePremium": limit_price,
            "stopPremium": provisional_stop,
            "targetPremium": provisional_target,
            "stopLossPct": stop_loss_pct,
            "takeProfitPct": take_profit_pct,
            "breakevenDecayPct": breakeven_decay_pct,
            "slMovedToBreakeven": False,
            "stopOrderId": None,
            "takeProfitOrderId": None,
            "bracketAttached": False,
            "lots": lots,
            "contractValue": cv,
            "entryOrderId": order.id,
            "entryLimitPrice": limit_price,
            "entryTime": bar.time,
            "createdAt": _now(),
            "updatedAt": _now(),
        }
        inserted = await self._trades.insert_one(pending_doc)
        pending_doc["_id"] = inserted.inserted_id

        filled_order = await self._await_limit_fill_or_cancel(
            api_key,
            api_secret,
            order,
            product=product,
            product_symbol=prod_symbol,
            fallback_limit=limit_price,
        )
        if filled_order is None:
            tech = (
                f"Limit entry cancelled user={user_id} direction={direction} "
                f"symbol={prod_symbol} limit={limit_price:.2f} orderId={order.id}"
            )
            log.warning("ST Options: %s", tech)
            self._push_activity(
                user_id,
                tech,
                user_message=f"Limit cancelled — setup skipped ({prod_symbol})",
                level="warn",
            )
            await self._publish_session(user_id)
            return

        order = filled_order
        filled_lots = _order_filled_size(order)
        if filled_lots > 0:
            lots = normalize_order_size(filled_lots)
        fill = float(order.average_fill_price or limit_price)
        await self._promote_pending_entry(
            user_id,
            pending_doc,
            fill=fill,
            lots=lots,
            product=product,
            api_key=api_key,
            api_secret=api_secret,
            recovered_from_position=False,
        )

    async def _open_live_hedge(
        self,
        user_id: str,
        main_doc: dict[str, Any],
        *,
        max_risk: float = DEFAULT_MAX_RISK,
    ) -> dict[str, Any] | None:
        """Limit-sell same-strike opposite option; freeze hedge SL and attach broker SL-only."""
        if _hedge_is_open(main_doc) or str(main_doc.get("hedgeStatus")) == HEDGE_STATUS_CLOSED:
            return main_doc
        strike = float(main_doc.get("strike") or 0)
        expiry_day = self._trade_expiry_date(main_doc)
        if strike <= 0 or expiry_day is None:
            return None
        coin = normalize_underlying(str(main_doc.get("underlying") or "BTC"))
        main_side = str(main_doc.get("optionSide") or self._option_side_from_doc(main_doc)).upper()
        hedge_side = opposite_option_side(main_side)
        hedge_symbol = delta_option_symbol(hedge_side, coin, strike, expiry_day)
        lots = int(main_doc.get("lots") or 1)
        await self._market.ensure_symbols({normalize_symbol(hedge_symbol)})

        try:
            product = await self._delta.fetch_product(hedge_symbol)
        except Exception:
            tech = (
                f"Hedge skip user={user_id} main={main_doc.get('optionSymbol')} "
                f"hedge={hedge_symbol} reason=product_missing"
            )
            log.exception("ST Options: %s", tech)
            self._push_activity(
                user_id,
                tech,
                user_message=f"Hedge skipped — {hedge_symbol} not available",
                level="warn",
            )
            return None

        ticker = self._market.latest_tickers.get(normalize_symbol(hedge_symbol))
        live_px = _ticker_premium(ticker)
        if live_px is None:
            try:
                inst = await self._delta.fetch_ticker(hedge_symbol)
                live_px = float(inst.mark_price or inst.close_price or 0) or None
            except Exception:
                live_px = None
        if live_px is None or float(live_px) <= 0:
            tech = (
                f"Hedge skip user={user_id} hedge={hedge_symbol} reason=no_live_premium"
            )
            log.warning("ST Options: %s", tech)
            self._push_activity(
                user_id,
                tech,
                user_message=f"Hedge skipped — no live price for {hedge_symbol}",
                level="warn",
            )
            return None

        limit_price = entry_limit_price(float(live_px))
        if limit_price is None:
            return None

        pair_id = str(main_doc.get("pairId") or uuid.uuid4())
        await self._trades.update_one(
            {"_id": main_doc["_id"], "status": STATUS_OPEN},
            {
                "$set": {
                    "pairId": pair_id,
                    "legRole": "main",
                    "optionSide": main_side,
                    "hedgeSymbol": hedge_symbol,
                    "hedgePending": True,
                    "hedgeStatus": HEDGE_STATUS_PENDING,
                    "updatedAt": _now(),
                }
            },
        )
        main_doc["pairId"] = pair_id
        main_doc["hedgeSymbol"] = hedge_symbol
        main_doc["hedgePending"] = True
        main_doc["hedgeStatus"] = HEDGE_STATUS_PENDING

        try:
            api_key, api_secret = await self._trade_credentials(user_id, main_doc)
            order = await self._delta.place_limit_entry(
                api_key,
                api_secret,
                product,
                "sell",
                normalize_order_size(float(lots)),
                limit_price,
            )
        except Exception as exc:
            tech = (
                f"Hedge skip user={user_id} hedge={hedge_symbol} reason=order_failed "
                f"limit={limit_price:.2f} "
                f"delta={_extract_delta_error_payload(exc).get('code') or type(exc).__name__}"
            )
            log.exception("ST Options: %s", tech)
            await self._trades.update_one(
                {"_id": main_doc["_id"]},
                {
                    "$set": {
                        "hedgePending": False,
                        "hedgeStatus": HEDGE_STATUS_NONE,
                        "updatedAt": _now(),
                    }
                },
            )
            main_doc["hedgePending"] = False
            main_doc["hedgeStatus"] = HEDGE_STATUS_NONE
            self._push_activity(
                user_id,
                tech,
                user_message=_order_failure_user_message(exc, kind="hedge"),
                level="warn",
            )
            return None

        filled_order = await self._await_limit_fill_or_cancel(
            api_key,
            api_secret,
            order,
            product=product,
            product_symbol=hedge_symbol,
            fallback_limit=limit_price,
        )
        if filled_order is None:
            tech = (
                f"Hedge skip user={user_id} hedge={hedge_symbol} reason=limit_unfilled "
                f"limit={limit_price:.2f} orderId={order.id}"
            )
            log.warning("ST Options: %s", tech)
            await self._trades.update_one(
                {"_id": main_doc["_id"]},
                {
                    "$set": {
                        "hedgePending": False,
                        "hedgeStatus": HEDGE_STATUS_NONE,
                        "updatedAt": _now(),
                    }
                },
            )
            main_doc["hedgePending"] = False
            main_doc["hedgeStatus"] = HEDGE_STATUS_NONE
            self._push_activity(
                user_id,
                tech,
                user_message=f"Hedge limit did not fill for {hedge_symbol}",
                level="warn",
            )
            return None

        order = filled_order
        filled_lots = _order_filled_size(order)
        if filled_lots > 0:
            lots = normalize_order_size(filled_lots)
        fill = float(order.average_fill_price or limit_price)
        cv = float(
            main_doc.get("contractValue")
            or contract_value_for(main_doc.get("underlying", "BTC"))
        )
        main_entry = float(main_doc.get("premiumReceived") or 0)
        main_live = float(
            main_doc["livePremium"]
            if main_doc.get("livePremium") is not None
            else main_entry
        )
        main_profit = short_option_pnl(main_entry, main_live, cv, lots)
        stop_px = hedge_stop_premium(fill, main_profit, float(max_risk), cv, lots)
        hedge_fields: dict[str, Any] = {
            "pairId": pair_id,
            "legRole": "main",
            "optionSide": main_side,
            "hedgeSymbol": hedge_symbol,
            "hedgePremiumReceived": fill,
            "hedgeLivePremium": fill,
            "hedgeEntryTime": int(_now().timestamp()),
            "hedgeEntryOrderId": order.id,
            "hedgeLots": lots,
            "hedgePending": False,
            "hedgeStatus": HEDGE_STATUS_OPEN,
            "hedgeMainProfitAtOpen": main_profit,
            "hedgeStopPremium": stop_px,
            "hedgeStopOrderId": None,
            "updatedAt": _now(),
        }
        await self._trades.update_one(
            {"_id": main_doc["_id"], "status": STATUS_OPEN},
            {"$set": hedge_fields},
        )
        main_doc.update(hedge_fields)
        if stop_px is not None:
            await self._attach_hedge_stop_protection(
                user_id, main_doc, product, api_key, api_secret, float(stop_px)
            )
        tech = (
            f"Hedge opened user={user_id} main={main_doc.get('optionSymbol')} "
            f"hedge={hedge_symbol} fill={fill:.2f} lots={lots} pairId={pair_id} "
            f"orderId={order.id} mainProfit={main_profit:.2f} hedgeStop={stop_px}"
        )
        log.info("ST Options: %s", tech)
        self._push_activity(
            user_id,
            tech,
            user_message=(
                f"Hedge opened ({hedge_symbol})"
                + (f" · protect at {float(stop_px):.2f}" if stop_px is not None else "")
            ),
            level="success",
        )
        return main_doc

    async def _attach_hedge_stop_protection(
        self,
        user_id: str,
        main_doc: dict[str, Any],
        product: ProductSummary,
        api_key: str,
        api_secret: str,
        stop_level: float,
    ) -> bool:
        """Place SL-only broker bracket on the hedge leg (frozen; never amended)."""
        symbol = str(main_doc.get("hedgeSymbol") or product.symbol)
        try:
            await self._delta.place_position_bracket(
                api_key,
                api_secret,
                product,
                stop_level,
                None,
            )
            legs = None
            for attempt in range(3):
                legs = await self._delta.find_bracket_legs(api_key, api_secret, symbol)
                if legs.stop_loss_order_id:
                    break
                if attempt < 2:
                    await asyncio.sleep(0.25 * (attempt + 1))
            stop_id = legs.stop_loss_order_id if legs else None
            if not stop_id:
                raise RuntimeError("Hedge stop order was not discoverable after placement")
            main_doc["hedgeStopOrderId"] = stop_id
            await self._trades.update_one(
                {"_id": main_doc["_id"], "status": STATUS_OPEN},
                {"$set": {"hedgeStopOrderId": stop_id, "updatedAt": _now()}},
            )
            return True
        except Exception as exc:
            tech = (
                f"Hedge bracket attach failed user={user_id} symbol={symbol} "
                f"stop={stop_level:.2f}; soft hedge stop monitoring active err={exc}"
            )
            log.exception("ST Options: %s", tech)
            self._push_activity(
                user_id,
                tech,
                user_message=f"Broker hedge stop could not be attached to {symbol}; monitoring here",
                level="warn",
            )
            return False

    async def _reconcile_hedge_broker_stop(self, user_id: str, doc: dict[str, Any]) -> bool:
        """If hedge broker SL filled, record hedge closed and flatten main. Returns True if handled."""
        stop_id = doc.get("hedgeStopOrderId")
        if not stop_id or not _hedge_is_open(doc):
            return False
        try:
            api_key, api_secret = await self._trade_credentials(user_id, doc)
            order = await self._delta.fetch_order(api_key, api_secret, int(stop_id))
        except Exception:
            return False
        if not _is_bracket_fill(order):
            return False
        exit_price = float(
            getattr(order, "average_fill_price", None)
            or doc.get("hedgeStopPremium")
            or doc.get("hedgeLivePremium")
            or doc.get("hedgePremiumReceived")
            or 0
        )
        # Mark hedge closed via sibling row without another reduce.
        await self._close_hedge_if_open(
            user_id,
            doc,
            hedge_reason="pair_stop",
            exit_premium=exit_price,
            broker_reduce=False,
        )
        main_live = doc.get("livePremium")
        await self._close_live_trade(
            user_id,
            doc,
            reason="max_loss",
            exit_premium=float(main_live) if main_live is not None else None,
        )
        return True

    async def _cancel_hedge_stop_leg(self, user_id: str, main_doc: dict[str, Any]) -> bool:
        """Cancel pending hedge SL before intentional pair exit."""
        stop_id = main_doc.get("hedgeStopOrderId")
        if not stop_id:
            return True
        try:
            api_key, api_secret = await self._trade_credentials(user_id, main_doc)
            order = await self._delta.fetch_order(api_key, api_secret, int(stop_id))
            if _is_bracket_fill(order):
                return False
            if _is_bracket_pending(order) or order is None:
                with contextlib.suppress(Exception):
                    await self._delta.cancel_order(api_key, api_secret, int(stop_id))
            await self._trades.update_one(
                {"_id": main_doc["_id"]},
                {"$unset": {"hedgeStopOrderId": ""}, "$set": {"updatedAt": _now()}},
            )
            main_doc.pop("hedgeStopOrderId", None)
            return True
        except Exception:
            log.exception(
                "ST Options: hedge stop cancel failed user=%s hedge=%s",
                user_id,
                main_doc.get("hedgeSymbol"),
            )
            return False

    async def _close_hedge_if_open(
        self,
        user_id: str,
        main_doc: dict[str, Any],
        *,
        hedge_reason: str = "pair_stop",
        exit_premium: float | None = None,
        broker_reduce: bool = True,
    ) -> bool:
        """Market-reduce open hedge leg and insert a closed sibling ledger row."""
        if not _hedge_is_open(main_doc):
            return True
        hedge_symbol = str(main_doc.get("hedgeSymbol") or "")
        lots = int(main_doc.get("hedgeLots") or main_doc.get("lots") or 1)
        cv = float(
            main_doc.get("contractValue")
            or contract_value_for(main_doc.get("underlying", "BTC"))
        )
        entry = float(main_doc.get("hedgePremiumReceived") or 0)
        premium = exit_premium
        if premium is None:
            ticker = self._market.latest_tickers.get(normalize_symbol(hedge_symbol))
            premium = _ticker_premium(ticker)
        if premium is None:
            premium = float(main_doc.get("hedgeLivePremium") or entry)

        close_order_id = None
        skip_settlement = exit_premium is not None
        if broker_reduce:
            # Already flat on the exchange — don't send another reduce.
            try:
                api_key_chk, api_secret_chk = await self._trade_credentials(user_id, main_doc)
                still_short = await self._find_short_option_position(
                    api_key_chk, api_secret_chk, hedge_symbol
                )
                if still_short is None:
                    if exit_premium is None:
                        after_ts = main_doc.get("hedgeEntryTime") or main_doc.get("entryTime")
                        try:
                            after_i = int(after_ts) if after_ts is not None else None
                        except (TypeError, ValueError):
                            after_i = None
                        looked = await self._lookup_cover_fill_price(
                            api_key_chk,
                            api_secret_chk,
                            hedge_symbol,
                            after_ts=after_i,
                        )
                        if looked is not None:
                            premium = looked
                    broker_reduce = False
                    skip_settlement = True
            except Exception:
                log.exception(
                    "ST Options: hedge flat-check failed user=%s hedge=%s",
                    user_id,
                    hedge_symbol,
                )
        if broker_reduce:
            stop_id = main_doc.get("hedgeStopOrderId")
            if stop_id:
                try:
                    api_key, api_secret = await self._trade_credentials(user_id, main_doc)
                    stop_order = await self._delta.fetch_order(
                        api_key, api_secret, int(stop_id)
                    )
                    if _is_bracket_fill(stop_order):
                        premium = float(
                            getattr(stop_order, "average_fill_price", None)
                            or main_doc.get("hedgeStopPremium")
                            or premium
                        )
                        broker_reduce = False
                        skip_settlement = True
                        await self._trades.update_one(
                            {"_id": main_doc["_id"]},
                            {
                                "$unset": {"hedgeStopOrderId": ""},
                                "$set": {"updatedAt": _now()},
                            },
                        )
                        main_doc.pop("hedgeStopOrderId", None)
                    elif _is_bracket_pending(stop_order) or stop_order is None:
                        with contextlib.suppress(Exception):
                            await self._delta.cancel_order(
                                api_key, api_secret, int(stop_id)
                            )
                        await self._trades.update_one(
                            {"_id": main_doc["_id"]},
                            {
                                "$unset": {"hedgeStopOrderId": ""},
                                "$set": {"updatedAt": _now()},
                            },
                        )
                        main_doc.pop("hedgeStopOrderId", None)
                except Exception:
                    log.exception(
                        "ST Options: hedge stop cancel/check failed user=%s hedge=%s",
                        user_id,
                        hedge_symbol,
                    )
            if broker_reduce:
                try:
                    product = await self._delta.fetch_product(hedge_symbol)
                    api_key, api_secret = await self._trade_credentials(user_id, main_doc)
                    order = await self._delta.place_market_reduce(
                        api_key, api_secret, product, "buy", lots
                    )
                    if order.average_fill_price:
                        premium = float(order.average_fill_price)
                    close_order_id = order.id
                except Exception as exc:
                    tech = (
                        f"Hedge close failed user={user_id} hedge={hedge_symbol} "
                        f"reason={hedge_reason} err={exc}"
                    )
                    log.exception("ST Options: %s", tech)
                    self._push_activity(
                        user_id,
                        tech,
                        user_message=f"Could not close hedge {hedge_symbol}",
                        level="warn",
                    )
                    return False
        elif not skip_settlement:
            # Settlement / force-close: intrinsic of opposite side when possible.
            expiry_day = self._trade_expiry_date(main_doc)
            strike = float(main_doc.get("strike") or 0)
            if expiry_day is not None and strike > 0:
                underlying = normalize_underlying(str(main_doc.get("underlying") or "BTC"))
                spot = await self._settlement_spot(underlying, expiry_day)
                if spot is not None:
                    hedge_side = opposite_option_side(
                        str(main_doc.get("optionSide") or self._option_side_from_doc(main_doc))
                    )
                    premium = settlement_intrinsic(
                        option_side=hedge_side,  # type: ignore[arg-type]
                        strike=strike,
                        settlement_spot=spot,
                    )

        pnl = short_option_pnl(entry, float(premium), cv, lots)
        exit_time = int(_now().timestamp())
        pair_id = main_doc.get("pairId") or str(uuid.uuid4())
        sibling = {
            "userId": user_id,
            "accountId": main_doc.get("accountId"),
            "direction": main_doc.get("direction"),
            "status": STATUS_CLOSED,
            "underlying": main_doc.get("underlying"),
            "date": main_doc.get("date"),
            "stColour": main_doc.get("stColour"),
            "stColourChangeTime": main_doc.get("stColourChangeTime"),
            "emaPrice": main_doc.get("emaPrice"),
            "strike": main_doc.get("strike"),
            "expiryDate": main_doc.get("expiryDate"),
            "optionSymbol": hedge_symbol,
            "optionSide": opposite_option_side(
                str(main_doc.get("optionSide") or self._option_side_from_doc(main_doc))
            ),
            "premiumReceived": entry,
            "exitPrice": float(premium),
            "exitReason": hedge_reason,
            "pnl": pnl,
            "lots": lots,
            "contractValue": cv,
            "entryTime": main_doc.get("hedgeEntryTime") or main_doc.get("entryTime"),
            "exitTime": exit_time,
            "closeOrderId": close_order_id,
            "entryOrderId": main_doc.get("hedgeEntryOrderId"),
            "pairId": pair_id,
            "legRole": "hedge",
            "createdAt": _now(),
            "updatedAt": _now(),
        }
        await self._trades.insert_one(sibling)
        await self._trades.update_one(
            {"_id": main_doc["_id"]},
            {
                "$set": {
                    "pairId": pair_id,
                    "hedgeStatus": HEDGE_STATUS_CLOSED,
                    "hedgePending": False,
                    "hedgeExitPrice": float(premium),
                    "hedgePnl": pnl,
                    "hedgeExitTime": exit_time,
                    "hedgeCloseOrderId": close_order_id,
                    "updatedAt": _now(),
                }
            },
        )
        main_doc["hedgeStatus"] = HEDGE_STATUS_CLOSED
        main_doc["hedgePending"] = False
        tech = (
            f"Hedge closed user={user_id} hedge={hedge_symbol} reason={hedge_reason} "
            f"exit={float(premium):.2f} pnl={pnl:.2f} orderId={close_order_id}"
        )
        log.info("ST Options: %s", tech)
        self._push_activity(
            user_id,
            tech,
            user_message=(
                f"Closed hedge {hedge_symbol} ({self._exit_reason_user(hedge_reason)}) · "
                f"result {pnl:.2f}"
            ),
            level="warn" if pnl < 0 else "success",
        )
        return True

    def _trade_expiry_date(self, doc: dict[str, Any]) -> date | None:
        raw = doc.get("expiryDate")
        if raw:
            try:
                return date.fromisoformat(str(raw)[:10])
            except ValueError:
                pass
        return parse_option_symbol_expiry(str(doc.get("optionSymbol") or ""))

    def _option_side_from_doc(self, doc: dict[str, Any]) -> str:
        symbol = str(doc.get("optionSymbol") or "").upper()
        if symbol.startswith("P-"):
            return "PUT"
        if symbol.startswith("C-"):
            return "CALL"
        direction = doc.get("direction")
        return "PUT" if direction == "LONG" else "CALL"

    async def _trade_credentials(
        self,
        user_id: str,
        doc: dict[str, Any],
    ) -> tuple[str, str]:
        user = await self._load_user(user_id)
        account_id = doc.get("accountId")
        account = None
        for row in await self._accounts.list_raw_accounts(user):
            if str(row.get("_id")) == str(account_id):
                account = row
                break
        if account is None:
            account = await self._selected_account(user)
        return self._credentials(account)

    async def _cancel_bracket_legs(self, user_id: str, doc: dict[str, Any]) -> BracketCancelResult:
        """Cancel pending broker protection before an intentional strategy exit.

        Only clears Mongo bracket IDs when legs are safely gone. If a leg already
        filled, returns that fill so callers can record the exit instead of reducing.
        """
        symbol = str(doc.get("optionSymbol") or "")
        if not doc.get("stopOrderId") and not doc.get("takeProfitOrderId") and not doc.get("bracketAttached"):
            return BracketCancelResult(ok=True, cleared=True)

        try:
            api_key, api_secret = await self._trade_credentials(user_id, doc)
            stop_id, target_id = await self._resolve_bracket_ids(
                user_id, doc, api_key, api_secret
            )

            stop_order = (
                await self._delta.fetch_order(api_key, api_secret, int(stop_id))
                if stop_id
                else None
            )
            target_order = (
                await self._delta.fetch_order(api_key, api_secret, int(target_id))
                if target_id
                else None
            )

            if _is_bracket_fill(stop_order):
                if target_id and _is_bracket_pending(target_order):
                    with contextlib.suppress(Exception):
                        await self._delta.cancel_order(api_key, api_secret, int(target_id))
                await self._clear_bracket_bookkeeping(doc)
                return BracketCancelResult(
                    ok=True,
                    filled_reason="stop_loss",
                    filled_order=stop_order,
                    cleared=True,
                )
            if _is_bracket_fill(target_order):
                if stop_id and _is_bracket_pending(stop_order):
                    with contextlib.suppress(Exception):
                        await self._delta.cancel_order(api_key, api_secret, int(stop_id))
                await self._clear_bracket_bookkeeping(doc)
                return BracketCancelResult(
                    ok=True,
                    filled_reason="take_profit",
                    filled_order=target_order,
                    cleared=True,
                )

            errors: list[str] = []
            for label, order_id, order in (
                ("stop", stop_id, stop_order),
                ("target", target_id, target_order),
            ):
                if not order_id:
                    continue
                if _is_bracket_cancelled(order):
                    continue
                if not _is_bracket_pending(order):
                    # Unknown terminal/non-pending state — do not invent success.
                    continue
                try:
                    await self._delta.cancel_order(api_key, api_secret, int(order_id))
                except Exception as exc:
                    errors.append(f"{label}:{exc}")
                    log.warning(
                        "ST Options: bracket cancel failed user=%s symbol=%s leg=%s orderId=%s",
                        user_id,
                        symbol,
                        label,
                        order_id,
                        exc_info=True,
                    )

            if errors:
                # Keep IDs so a later tick can still reconcile / retry cancel.
                return BracketCancelResult(ok=False, cleared=False)

            await self._clear_bracket_bookkeeping(doc)
            return BracketCancelResult(ok=True, cleared=True)
        except Exception:
            log.warning(
                "ST Options: could not cancel bracket user=%s symbol=%s",
                user_id,
                symbol,
                exc_info=True,
            )
            return BracketCancelResult(ok=False, cleared=False)

    async def _force_close_expiring(self, user_id: str, config: dict[str, Any]) -> None:
        """Square-off same-day opens at 17:15 IST; settle anything already past settlement."""
        now = _now()
        now_ist = now.astimezone(IST)
        today = now_ist.date()
        open_trades = await self._list_trade_docs(user_id, status=STATUS_OPEN)
        for doc in open_trades:
            expiry_day = self._trade_expiry_date(doc)
            if expiry_day is None:
                continue
            settle_ts = settlement_unix(expiry_day)
            if int(now.timestamp()) >= settle_ts:
                await self._settle_expired_trade(user_id, doc, reason="expired")
                continue
            if expiry_day == today and now_ist.time() >= FORCE_CLOSE_IST:
                await self._close_live_trade(
                    user_id, doc, reason="expiry_close", exit_premium=None
                )

    async def _settlement_spot(self, underlying: str, expiry_day: date) -> float | None:
        """Perp close of the 1H bar ending at settlement (17:30 IST) on expiry day."""
        settle_ts = settlement_unix(expiry_day)
        bars = await self._fetch_perp_bars(underlying, end=_now(), days=max(WARMUP_DAYS, 5))
        # Prefer the bar whose close time equals settlement.
        for bar in reversed(bars):
            if bar.time + RESOLUTION_SECONDS == settle_ts:
                return float(bar.close)
        # Fallback: last closed bar at or before settlement.
        prior = [b for b in bars if b.time + RESOLUTION_SECONDS <= settle_ts]
        if prior:
            return float(prior[-1].close)
        return None

    async def _settle_expired_trade(
        self,
        user_id: str,
        doc: dict[str, Any],
        *,
        reason: str = "expired",
    ) -> bool:
        """Mark an expired/delisted open trade closed using settlement intrinsic (no broker order)."""
        if doc.get("status") != STATUS_OPEN:
            return False
        cancel = await self._cancel_bracket_legs(user_id, doc)
        if cancel.filled_reason and cancel.filled_order is not None:
            fallback_price = (
                doc.get("stopPremium")
                if cancel.filled_reason == "stop_loss"
                else doc.get("targetPremium")
            )
            exit_price = float(
                getattr(cancel.filled_order, "average_fill_price", None)
                or fallback_price
                or doc.get("livePremium")
                or doc.get("premiumReceived")
                or 0
            )
            await self._record_broker_bracket_exit(
                user_id,
                doc,
                reason=cancel.filled_reason,
                exit_price=exit_price,
                close_order_id=int(getattr(cancel.filled_order, "id", 0) or 0),
            )
            return True
        # Settlement / force-close must proceed even if cancel failed (DB-only close).
        symbol = doc.get("optionSymbol")
        entry = float(doc.get("premiumReceived") or 0)
        lots = int(doc.get("lots") or 1)
        cv = float(doc.get("contractValue") or contract_value_for(doc.get("underlying", "BTC")))
        strike = float(doc.get("strike") or 0)
        side = self._option_side_from_doc(doc)  # type: ignore[arg-type]
        expiry_day = self._trade_expiry_date(doc)
        underlying = normalize_underlying(str(doc.get("underlying") or "BTC"))

        exit_px: float | None = None
        if expiry_day is not None and strike > 0:
            spot = await self._settlement_spot(underlying, expiry_day)
            if spot is not None:
                exit_px = settlement_intrinsic(
                    option_side=side,  # type: ignore[arg-type]
                    strike=strike,
                    settlement_spot=spot,
                )
        if exit_px is None:
            live = doc.get("livePremium")
            exit_px = float(live) if live is not None else entry

        pnl = short_option_pnl(entry, float(exit_px), cv, lots)
        result = await self._trades.update_one(
            {"_id": doc["_id"], "status": STATUS_OPEN},
            {
                "$set": {
                    "status": STATUS_CLOSED,
                    "exitPrice": float(exit_px),
                    "exitReason": reason,
                    "pnl": pnl,
                    "exitTime": int(_now().timestamp()),
                    "closeOrderId": None,
                    "updatedAt": _now(),
                },
                "$unset": {"closeError": ""},
            },
        )
        if not result.modified_count:
            return False
        tech = (
            f"Settled user={user_id} symbol={symbol} reason={reason} "
            f"exit={float(exit_px):.2f} pnl={pnl:.2f}"
        )
        log.info("ST Options: %s", tech)
        self._push_activity(
            user_id,
            tech,
            user_message=(
                f"Closed {symbol} ({self._exit_reason_user(reason)}) · result {pnl:.2f}"
            ),
            level="warn" if pnl < 0 else "success",
        )
        await self._close_hedge_if_open(
            user_id,
            doc,
            hedge_reason="pair_stop",
            broker_reduce=False,
        )
        return True

    async def force_close_trade(self, user: dict[str, Any], trade_id: str) -> dict[str, Any]:
        """Operator escape hatch: mark open trade closed in Mongo without broker reduce."""
        try:
            oid = ObjectId(trade_id)
        except Exception as exc:
            raise http_error(400, "Invalid trade id") from exc
        doc = await self._trades.find_one({"_id": oid, "userId": user["id"]})
        if not doc:
            raise http_error(404, "Trade not found")
        if doc.get("status") != STATUS_OPEN:
            raise http_error(400, "Trade is not open")
        ok = await self._settle_expired_trade(user["id"], doc, reason="force_closed")
        if not ok:
            raise http_error(500, "Could not force-close trade")
        await self._publish_session(user["id"])
        return await self.live_snapshot(user)

    async def _record_broker_bracket_exit(
        self,
        user_id: str,
        doc: dict[str, Any],
        *,
        reason: str,
        exit_price: float,
        close_order_id: int,
        hedge_exit_premium: float | None = None,
        hedge_broker_reduce: bool = True,
    ) -> None:
        """Record an SL/TP already executed by Delta without sending another reduce."""
        entry = float(doc.get("premiumReceived") or 0)
        lots = int(doc.get("lots") or 1)
        cv = float(doc.get("contractValue") or contract_value_for(doc.get("underlying", "BTC")))
        pnl = short_option_pnl(entry, exit_price, cv, lots)
        result = await self._trades.update_one(
            {"_id": doc["_id"], "status": STATUS_OPEN},
            {
                "$set": {
                    "status": STATUS_CLOSED,
                    "exitPrice": exit_price,
                    "exitReason": reason,
                    "pnl": pnl,
                    "exitTime": int(_now().timestamp()),
                    "closeOrderId": close_order_id,
                    "bracketAttached": False,
                    "updatedAt": _now(),
                },
                "$unset": {
                    "closeError": "",
                    "bracketError": "",
                    "stopOrderId": "",
                    "takeProfitOrderId": "",
                },
            },
        )
        if not result.modified_count:
            return
        symbol = doc.get("optionSymbol")
        tech = (
            f"Broker bracket filled user={user_id} direction={doc.get('direction')} "
            f"symbol={symbol} reason={reason} exit={exit_price:.2f} pnl={pnl:.2f} "
            f"orderId={close_order_id}"
            if reason != "broker_flat"
            else (
                f"Broker flat user={user_id} direction={doc.get('direction')} "
                f"symbol={symbol} exit={exit_price:.2f} pnl={pnl:.2f}"
            )
        )
        log.info("ST Options: %s", tech)
        self._push_activity(
            user_id,
            tech,
            user_message=(
                f"Closed {symbol} ({self._exit_reason_user(reason)}) · result {pnl:.2f}"
            ),
            level="warn" if pnl < 0 else "success",
        )
        await self._close_hedge_if_open(
            user_id,
            doc,
            hedge_reason="pair_stop" if reason != "broker_flat" else "broker_flat",
            exit_premium=hedge_exit_premium,
            broker_reduce=hedge_broker_reduce,
        )
        await self._maybe_reenter_after_close(user_id, doc, reason)

    async def _maybe_reenter_after_close(
        self,
        user_id: str,
        doc: dict[str, Any],
        reason: str,
    ) -> None:
        if reason not in {"take_profit", "expiry_close"}:
            return
        config = await self.get_config({"id": user_id})
        try:
            bars = await self._fetch_perp_bars(config["underlying"], end=_now(), days=WARMUP_DAYS)
            now_ts = int(_now().timestamp())
            closed_bars = [b for b in bars if b.time + RESOLUTION_SECONDS <= now_ts]
            inds = compute_indicator_bars(
                closed_bars,
                st_period=int(config["stPeriod"]),
                st_multiplier=float(config["stMultiplier"]),
                ema_length=int(config["emaLength"]),
            )
            direction = doc["direction"]
            max_st_dist = float(config.get("maxStDistancePct") or 0)
            if inds and entry_ready(inds[-1], direction) and st_distance_within(inds[-1], max_st_dist):
                existing = await self._trades.find_one(
                    {"userId": user_id, "status": STATUS_OPEN, "direction": direction}
                )
                if not existing:
                    await self._open_live_trade(user_id, config, inds[-1], direction)
        except Exception:
            log.exception("ST Options TP/expiry re-entry failed")

    async def _close_live_trade(
        self,
        user_id: str,
        doc: dict[str, Any],
        *,
        reason: str,
        exit_premium: float | None,
    ) -> bool:
        """Buy-to-cover on Delta and mark Mongo closed. Returns True only on successful close."""
        if (
            doc.get("bracketAttached")
            or doc.get("stopOrderId")
            or doc.get("takeProfitOrderId")
        ):
            bracket_state = await self._reconcile_broker_bracket(user_id, doc)
            if bracket_state == "closed":
                return True
        symbol = doc.get("optionSymbol")
        lots = int(doc.get("lots") or 1)
        cv = float(doc.get("contractValue") or contract_value_for(doc.get("underlying", "BTC")))
        entry = float(doc.get("premiumReceived") or 0)
        premium = exit_premium
        if premium is None:
            ticker = self._market.latest_tickers.get(normalize_symbol(symbol or ""))
            if ticker:
                premium = ticker.mark_price or ticker.last_price
        if premium is None:
            premium = entry

        cancel = await self._cancel_bracket_legs(user_id, doc)
        if cancel.filled_reason and cancel.filled_order is not None:
            fallback_price = (
                doc.get("stopPremium")
                if cancel.filled_reason == "stop_loss"
                else doc.get("targetPremium")
            )
            exit_price = float(
                getattr(cancel.filled_order, "average_fill_price", None)
                or fallback_price
                or premium
                or 0
            )
            await self._record_broker_bracket_exit(
                user_id,
                doc,
                reason=cancel.filled_reason,
                exit_price=exit_price,
                close_order_id=int(getattr(cancel.filled_order, "id", 0) or 0),
            )
            return True
        if not cancel.ok:
            tech = (
                f"Close blocked user={user_id} symbol={symbol} reason={reason} "
                f"direction={doc.get('direction')} pending_brackets=true"
            )
            log.warning("ST Options: %s", tech)
            await self._trades.update_one(
                {"_id": doc["_id"], "status": STATUS_OPEN},
                {
                    "$set": {
                        "closeError": "bracket_cancel_failed",
                        "updatedAt": _now(),
                    }
                },
            )
            self._push_activity(
                user_id,
                tech,
                user_message=f"Could not close {symbol} — broker stop/target still pending",
                level="warn",
            )
            return False

        product_missing = False
        try:
            product = await self._delta.fetch_product(symbol)
            api_key, api_secret = await self._trade_credentials(user_id, doc)
            order = await self._delta.place_market_reduce(api_key, api_secret, product, "buy", lots)
            if order.average_fill_price:
                premium = float(order.average_fill_price)
            close_order_id = order.id
        except Exception as exc:
            product_missing = self._is_product_missing_error(exc)
            expiry_day = self._trade_expiry_date(doc)
            past_settlement = False
            if expiry_day is not None:
                past_settlement = int(_now().timestamp()) >= settlement_unix(expiry_day)
            if past_settlement:
                settled = await self._settle_expired_trade(user_id, doc, reason="expired")
                if settled:
                    return True
            tech = (
                f"Close failed user={user_id} symbol={symbol} reason={reason} "
                f"direction={doc.get('direction')} product_missing={product_missing}"
            )
            log.exception("ST Options: %s", tech)
            await self._trades.update_one(
                {"_id": doc["_id"], "status": STATUS_OPEN},
                {
                    "$set": {
                        "closeError": "product_missing" if product_missing else "close_failed",
                        "updatedAt": _now(),
                    }
                },
            )
            self._push_activity(
                user_id,
                tech,
                user_message=(
                    f"Could not close {symbol} — contract missing"
                    if product_missing
                    else f"Could not close {symbol} — still open"
                ),
                level="warn",
            )
            return False

        pnl = short_option_pnl(entry, float(premium), cv, lots)
        result = await self._trades.update_one(
            {"_id": doc["_id"], "status": STATUS_OPEN},
            {
                "$set": {
                    "status": STATUS_CLOSED,
                    "exitPrice": float(premium),
                    "exitReason": reason,
                    "pnl": pnl,
                    "exitTime": int(_now().timestamp()),
                    "closeOrderId": close_order_id,
                    "updatedAt": _now(),
                },
                "$unset": {"closeError": ""},
            },
        )
        if not result.modified_count:
            return True
        tech = (
            f"Closed user={user_id} direction={doc.get('direction')} symbol={symbol} "
            f"reason={reason} exit={float(premium):.2f} pnl={pnl:.2f} orderId={close_order_id}"
        )
        log.info("ST Options: %s", tech)
        self._push_activity(
            user_id,
            tech,
            user_message=(
                f"Closed {symbol} ({self._exit_reason_user(reason)}) · result {pnl:.2f}"
            ),
            level="warn" if pnl < 0 else "success",
        )

        await self._close_hedge_if_open(user_id, doc, hedge_reason="pair_stop")
        await self._maybe_reenter_after_close(user_id, doc, reason)
        return True

    @staticmethod
    def _is_product_missing_error(exc: BaseException) -> bool:
        text = str(exc).lower()
        needles = (
            "not found",
            "does not exist",
            "product_missing",
            "no such product",
            "unknown product",
            "invalid product",
            "404",
        )
        return any(n in text for n in needles)

    async def _run_backtest_job(
        self,
        user_id: str,
        job_id: str,
        *,
        underlying: str,
        max_risk: float,
        st_period: int,
        st_multiplier: float,
        ema_length: int,
        min_premium_pct: float,
        stop_loss_pct: float = DEFAULT_STOP_LOSS_PCT,
        take_profit_pct: float = DEFAULT_TAKE_PROFIT_PCT,
        breakeven_decay_pct: float = DEFAULT_BREAKEVEN_DECAY_PCT,
        dynamic_sizing: DynamicSizingConfig | None = None,
        strike_select_mode: str = DEFAULT_STRIKE_SELECT_MODE,
        strike_type: str = DEFAULT_STRIKE_TYPE,
        min_premium_abs: float = DEFAULT_MIN_PREMIUM_ABS,
        one_trade_per_formation: bool = False,
        skip_setups_after_target: int = DEFAULT_SKIP_SETUPS_AFTER_TARGET,
        max_st_distance_pct: float = DEFAULT_MAX_ST_DISTANCE_PCT,
        pair_hedge_enabled: bool = False,
        pair_hedge_mode: str = "immediate",
        pair_hedge_decay_pct: float = DEFAULT_PAIR_HEDGE_DECAY_PCT,
        from_date: date,
        to_date: date,
    ) -> None:
        job = self._backtest_jobs.get(user_id)
        if not job or job["id"] != job_id:
            return

        dyn = dynamic_sizing or DynamicSizingConfig()
        mode = str(strike_select_mode or DEFAULT_STRIKE_SELECT_MODE).strip().lower()
        skip_n = max(0, int(skip_setups_after_target))
        pair_on = bool(pair_hedge_enabled)
        pair_mode = normalize_pair_hedge_mode(pair_hedge_mode)
        pair_decay = float(pair_hedge_decay_pct)
        settings_snapshot = {
            "underlying": underlying,
            "maxRisk": max_risk,
            "stPeriod": st_period,
            "stMultiplier": st_multiplier,
            "emaLength": ema_length,
            "minPremiumPct": min_premium_pct,
            "stopLossPct": stop_loss_pct,
            "takeProfitPct": take_profit_pct,
            "breakevenDecayPct": breakeven_decay_pct,
            "dynamicSizingEnabled": dyn.enabled,
            "dynAfterLosses": dyn.after_losses,
            "dynIncreasePct": dyn.increase_pct,
            "dynMaxRiskPct": dyn.max_risk_pct,
            "dynAfterProfits": dyn.after_profits,
            "dynDecreasePct": dyn.decrease_pct,
            "strikeSelectMode": mode,
            "strikeType": strike_type,
            "minPremiumAbs": min_premium_abs,
            "oneTradePerFormation": bool(one_trade_per_formation),
            "skipSetupsAfterTarget": skip_n,
            "maxStDistancePct": float(max_st_distance_pct),
            "pairHedgeEnabled": pair_on,
            "pairHedgeMode": pair_mode,
            "pairHedgeDecayPct": pair_decay,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
        }

        def trace(msg: str, progress: int | None = None, stage: str | None = None) -> None:
            job["trace"].append(msg)
            if progress is not None:
                job["progress"] = progress
            if stage:
                job["stage"] = stage
            self.broadcaster.publish(
                user_id,
                {"type": "st_options_session", "topic": "st_options", "backtestJob": self._job_public(job)},
            )

        try:
            trace("Fetching perp candles…", 5, "candles")
            start_dt = datetime(from_date.year, from_date.month, from_date.day, tzinfo=IST) - timedelta(
                days=WARMUP_DAYS
            )
            end_dt = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59, tzinfo=IST)
            bars = await self._fetch_perp_bars_range(underlying, start_dt, end_dt)
            window_start = int(datetime(from_date.year, from_date.month, from_date.day, tzinfo=IST).timestamp())
            candle_end = int(end_dt.timestamp())
            trace(f"Loaded {len(bars)} 1H bars", 15, "products")

            coin = normalize_underlying(underlying)
            expiries: set[date] = set()
            for bar in bars:
                if bar.time < window_start:
                    continue
                for _, exp in expiry_dates_t0_t1(bar_close_unix(bar.time)):
                    expiries.add(exp)

            products_by_expiry: dict[date, list[ProductSummary]] = {}
            sorted_expiries = sorted(expiries)
            sem = asyncio.Semaphore(BACKTEST_FETCH_CONCURRENCY)
            done_products = {"n": 0}

            async def load_expiry(exp: date) -> tuple[date, list[ProductSummary]]:
                async with sem:
                    live, expired = await asyncio.gather(
                        self._delta.fetch_products_filtered(
                            underlying=coin,
                            expiry_date=exp.isoformat(),
                            contract_types="call_options,put_options",
                            states="live",
                            max_pages=3,
                        ),
                        self._delta.fetch_expired_option_products(
                            coin, exp.isoformat(), max_pages=5
                        ),
                    )
                done_products["n"] += 1
                n = done_products["n"]
                if n == 1 or n % 5 == 0 or n == len(sorted_expiries):
                    trace(
                        f"Products {n}/{len(sorted_expiries)}",
                        15 + int(40 * n / max(1, len(sorted_expiries))),
                        "products",
                    )
                return exp, live + expired

            if sorted_expiries:
                loaded = await asyncio.gather(*(load_expiry(exp) for exp in sorted_expiries))
                for exp, products in loaded:
                    products_by_expiry[exp] = products

            symbol_by_key: dict[tuple, str] = {}
            for exp, products in products_by_expiry.items():
                for product in products:
                    if product.strike_price is None:
                        continue
                    if not product_matches_expiry(product, exp):
                        continue
                    symbol_by_key[(exp, float(product.strike_price), _product_side(product))] = product.symbol

            perp_closes = [b.close for b in bars if b.time >= window_start] or [b.close for b in bars]
            ladder_depth = 10 if mode in {"fixed", "min_abs"} else 3
            band = strike_band_min_max(perp_closes, coin, depth=ladder_depth)
            load_symbols = sorted(
                {
                    p.symbol
                    for exp, products in products_by_expiry.items()
                    for p in products
                    if p.strike_price is not None
                    and product_matches_expiry(p, exp)
                    and strike_in_band(float(p.strike_price), band)
                    and p.symbol
                }
            )

            option_ohlc: dict[str, dict[int, tuple[float, float, float]]] = {}
            option_keys: dict[str, list[int]] = {}

            async def fetch_one_symbol(sym: str) -> None:
                if not sym or sym in option_ohlc:
                    return
                start_ts, end_ts = _option_candle_window(sym, window_start, candle_end)
                try:
                    async with sem:
                        raw = await self._delta.fetch_candles(sym, RESOLUTION, start_ts, end_ts)
                    series = {
                        int(c.time): (float(c.high), float(c.low), float(c.close)) for c in raw
                    }
                except Exception:
                    series = {}
                option_ohlc[sym] = series
                option_keys[sym] = sorted(series.keys())

            async def ensure_option_candles(symbols: list[str]) -> None:
                missing = [s for s in symbols if s and s not in option_ohlc]
                if not missing:
                    return
                await asyncio.gather(*(fetch_one_symbol(sym) for sym in missing))

            trace(f"Loading {len(load_symbols)} option candle series…", 60, "option_candles")
            if load_symbols:
                batch = 24
                for i in range(0, len(load_symbols), batch):
                    chunk = load_symbols[i : i + batch]
                    await ensure_option_candles(chunk)
                    done = min(i + batch, len(load_symbols))
                    job["progress"] = 60 + int(25 * done / max(1, len(load_symbols)))
                    self.broadcaster.publish(
                        user_id,
                        {
                            "type": "st_options_session",
                            "topic": "st_options",
                            "backtestJob": self._job_public(job),
                        },
                    )

            def _lookup_series(symbol: str, t: int) -> tuple[float, float, float] | None:
                series = option_ohlc.get(symbol) or {}
                if t in series:
                    return series[t]
                keys = option_keys.get(symbol) or []
                if not keys:
                    return None
                idx = bisect.bisect_right(keys, t) - 1
                if idx < 0:
                    return None
                return series[keys[idx]]

            def premium_lookup(symbol: str, expiry: date, strike: float, side: str) -> float | None:
                prod_symbol = symbol_by_key.get((expiry, float(strike), side)) or symbol
                hit = _lookup_series(prod_symbol, entry_bar_time["t"])
                return hit[2] if hit else None

            def option_candle_lookup(symbol: str, bar_time: int) -> tuple[float | None, float | None, float | None]:
                hit = _lookup_series(symbol, bar_time)
                if hit is None:
                    return None, None, None
                return hit[0], hit[1], hit[2]

            def classify_resolve_skip(perp_price: float, bar_unix: int, direction: Direction) -> str:
                side = option_side_for_direction(direction)
                saw_premium = False
                for _offset, expiry in eligible_expiries(bar_unix):
                    for _steps, strike in strike_ladder(
                        perp_price, side, coin, otm_depth=ladder_depth, itm_depth=ladder_depth
                    ):
                        symbol = delta_option_symbol(side, coin, strike, expiry)
                        prem = premium_lookup(symbol, expiry, strike, side)
                        if prem is not None and prem > 0:
                            saw_premium = True
                return "no_premium" if saw_premium else "no_contract"

            async def ensure_waterfall_candles(perp_price: float, bar_unix: int, direction: Direction) -> None:
                side = option_side_for_direction(direction)
                needed: list[str] = []
                for _offset, expiry in eligible_expiries(bar_unix):
                    for _steps, strike in strike_ladder(
                        perp_price, side, coin, otm_depth=ladder_depth, itm_depth=ladder_depth
                    ):
                        constructed = delta_option_symbol(side, coin, strike, expiry)
                        prod_symbol = symbol_by_key.get((expiry, float(strike), side)) or constructed
                        if prod_symbol not in option_ohlc:
                            needed.append(prod_symbol)
                if needed:
                    await ensure_option_candles(needed)

            entry_bar_time = {"t": 0}
            inds = compute_indicator_bars(
                bars, st_period=st_period, st_multiplier=st_multiplier, ema_length=ema_length
            )
            sizing = DynamicSizingState.create(float(max_risk), dyn)
            cv = contract_value_for(underlying)
            open_long: OpenTrade | None = None
            open_short: OpenTrade | None = None
            closed: list = []
            reenter_long = False
            reenter_short = False
            # When oneTradePerFormation: after any exit, block that side until st_colour changes.
            blocked_long_colour: str | None = None
            blocked_short_colour: str | None = None
            formation_gate = bool(one_trade_per_formation)
            # After take_profit: skip next N entry signals on that side.
            skip_long_left = 0
            skip_short_left = 0
            diagnostics = {
                "barsInWindow": 0,
                "entrySignals": 0,
                "opened": 0,
                "skippedNoContract": 0,
                "skippedNoPremium": 0,
                "skippedFormation": 0,
                "skippedAfterTarget": 0,
                "skippedStDistance": 0,
                "skippedPairHedge": 0,
            }

            trace("Simulating…", 90, "simulate")
            for bar in inds:
                if bar.time < window_start or bar.ema is None or bar.st.st_line is None:
                    continue
                diagnostics["barsInWindow"] += 1
                colour = bar.st_colour or "green"
                if formation_gate:
                    blocked_long_colour = clear_formation_block(
                        blocked_colour=blocked_long_colour, current_colour=colour
                    )
                    blocked_short_colour = clear_formation_block(
                        blocked_colour=blocked_short_colour, current_colour=colour
                    )

                before_len = len(closed)
                open_long, reenter_long = _manage_open(
                    open_long,
                    bar,
                    closed,
                    option_candle_lookup=option_candle_lookup,
                    reenter_flag=reenter_long,
                    take_profit_pct=take_profit_pct,
                )
                open_short, reenter_short = _manage_open(
                    open_short,
                    bar,
                    closed,
                    option_candle_lookup=option_candle_lookup,
                    reenter_flag=reenter_short,
                    take_profit_pct=take_profit_pct,
                )
                for newly in closed[before_len:]:
                    sizing.on_closed(newly.pnl)
                    armed = arm_skip_after_take_profit(
                        exit_reason=str(newly.exit_reason or ""),
                        skip_n=skip_n,
                    )
                    if armed is not None:
                        if newly.direction == "LONG":
                            skip_long_left = armed
                        else:
                            skip_short_left = armed
                    if formation_gate:
                        if newly.direction == "LONG":
                            blocked_long_colour = newly.st_colour or colour
                            reenter_long = False
                        else:
                            blocked_short_colour = newly.st_colour or colour
                            reenter_short = False
                if formation_gate:
                    reenter_long = False
                    reenter_short = False

                for direction in ("LONG", "SHORT"):
                    current = open_long if direction == "LONG" else open_short
                    reenter = reenter_long if direction == "LONG" else reenter_short
                    blocked = blocked_long_colour if direction == "LONG" else blocked_short_colour
                    skip_left = skip_long_left if direction == "LONG" else skip_short_left
                    signal_ok = entry_ready(bar, direction) or (reenter and not formation_gate)  # type: ignore[arg-type]
                    if current is not None or not signal_ok:
                        continue
                    if not st_distance_within(bar, max_st_distance_pct):
                        diagnostics["skippedStDistance"] += 1
                        continue
                    if formation_blocks_entry(
                        enabled=formation_gate, blocked_colour=blocked, current_colour=colour
                    ):
                        diagnostics["skippedFormation"] += 1
                        continue
                    should_skip, next_skip = consume_skip_setup(skip_left)
                    if should_skip:
                        diagnostics["skippedAfterTarget"] += 1
                        if direction == "LONG":
                            skip_long_left = next_skip
                            reenter_long = False
                        else:
                            skip_short_left = next_skip
                            reenter_short = False
                        continue
                    diagnostics["entrySignals"] += 1
                    entry_bar_time["t"] = bar.time
                    bar_unix = bar_close_unix(bar.time)
                    await ensure_waterfall_candles(bar.close, bar_unix, direction)  # type: ignore[arg-type]
                    resolved = resolve_backtest_strike(
                        mode=mode,
                        underlying=underlying,
                        direction=direction,  # type: ignore[arg-type]
                        perp_price=bar.close,
                        bar_close_unix=bar_unix,
                        premium_lookup=premium_lookup,
                        min_premium_pct=min_premium_pct,
                        min_premium_abs=min_premium_abs,
                        strike_type=strike_type,
                        st_line=float(bar.st.st_line) if bar.st.st_line is not None else None,
                    )
                    if resolved is None:
                        skip = classify_resolve_skip(bar.close, bar_unix, direction)  # type: ignore[arg-type]
                        if skip == "no_premium":
                            diagnostics["skippedNoPremium"] += 1
                        else:
                            diagnostics["skippedNoContract"] += 1
                        continue
                    prod_symbol = (
                        symbol_by_key.get((resolved.expiry, float(resolved.strike), resolved.option_side))
                        or resolved.symbol
                    )
                    if prod_symbol not in option_ohlc:
                        await ensure_option_candles([prod_symbol])
                    prem = resolved.premium
                    series = option_ohlc.get(prod_symbol) or {}
                    if bar.time in series:
                        prem = series[bar.time][2]
                    opened = OpenTrade(
                        direction=direction,  # type: ignore[arg-type]
                        entry_time=bar.time,
                        st_colour=colour,
                        st_colour_change_time=bar.st_colour_change_time,
                        ema_price=float(bar.ema),
                        strike=resolved.strike,
                        expiry=resolved.expiry.isoformat(),
                        option_symbol=prod_symbol,
                        premium_received=float(prem),
                        contract_value=resolved.contract_value or cv,
                        lots=sizing.lots_for_entry(float(prem), float(stop_loss_pct), resolved.contract_value or cv),
                        stop_loss_pct=float(stop_loss_pct),
                        breakeven_decay_pct=float(breakeven_decay_pct),
                    )
                    if pair_on:
                        hedge_side = opposite_option_side(resolved.option_side)
                        hedge_sym = (
                            symbol_by_key.get((resolved.expiry, float(resolved.strike), hedge_side))
                            or delta_option_symbol(
                                hedge_side, underlying, float(resolved.strike), resolved.expiry
                            )
                        )
                        if hedge_sym not in option_ohlc:
                            await ensure_option_candles([hedge_sym])
                        hedge_series = option_ohlc.get(hedge_sym) or {}
                        hedge_prem = None
                        if bar.time in hedge_series:
                            hedge_prem = hedge_series[bar.time][2]
                        if hedge_prem is None or float(hedge_prem) <= 0:
                            diagnostics["skippedPairHedge"] += 1
                        else:
                            pair_id = str(uuid.uuid4())
                            opened.pair_id = pair_id
                            opened.pair_hedge_mode = pair_mode
                            opened.pair_hedge_decay_pct = pair_decay
                            opened.main_option_side = str(resolved.option_side)
                            opened.hedge_symbol = hedge_sym
                            if pair_mode == "immediate":
                                opened.hedge_premium_received = float(hedge_prem)
                                opened.hedge_entry_time = bar.time
                                opened.hedge_pending = False
                            else:
                                opened.hedge_pending = True
                    diagnostics["opened"] += 1
                    if direction == "LONG":
                        open_long = opened
                        reenter_long = False
                    else:
                        open_short = opened
                        reenter_short = False

            if inds:
                last = inds[-1]
                for side_trade in (open_long, open_short):
                    if side_trade is None:
                        continue
                    if side_trade.option_symbol not in option_ohlc:
                        await ensure_option_candles([side_trade.option_symbol])
                    if side_trade.hedge_symbol and side_trade.hedge_symbol not in option_ohlc:
                        await ensure_option_candles([side_trade.hedge_symbol])
                    _h, _l, close = option_candle_lookup(side_trade.option_symbol, last.time)
                    exit_px = close if close is not None else side_trade.premium_received
                    row = _close_trade(side_trade, last.time, float(exit_px), "end_of_data")
                    sizing.on_closed(row.pnl)
                    closed.append(row)
                    if (
                        side_trade.hedge_symbol
                        and side_trade.hedge_premium_received is not None
                    ):
                        _hh, _hl, hclose = option_candle_lookup(side_trade.hedge_symbol, last.time)
                        hedge_exit = (
                            float(hclose)
                            if hclose is not None
                            else float(side_trade.hedge_premium_received)
                        )
                        hrow = _close_hedge_leg(side_trade, last.time, hedge_exit, "end_of_data")
                        sizing.on_closed(hrow.pnl)
                        closed.append(hrow)

            result = BacktestResult(
                trades=closed,
                summary=compute_summary(closed),
                settings=settings_snapshot,
            )
            public = _public_backtest_result(result, diagnostics)
            job["result"] = public
            job["status"] = "completed"
            job["progress"] = 100
            job["stage"] = "done"
            with contextlib.suppress(Exception):
                run_id = await self._persist_backtest_run(
                    user_id,
                    settings=settings_snapshot,
                    result=public,
                    status="completed",
                )
                job["runId"] = run_id
            trace(
                f"Done — {len(closed)} trades "
                f"(signals={diagnostics['entrySignals']}, "
                f"skipContract={diagnostics['skippedNoContract']}, "
                f"skipPremium={diagnostics['skippedNoPremium']})",
                100,
                "done",
            )
        except Exception as exc:
            log.exception("ST Options backtest failed")
            job["status"] = "failed"
            job["error"] = str(exc)
            job["stage"] = "failed"
            with contextlib.suppress(Exception):
                run_id = await self._persist_backtest_run(
                    user_id,
                    settings=settings_snapshot,
                    result=None,
                    status="failed",
                    error=str(exc),
                )
                job["runId"] = run_id
            self.broadcaster.publish(
                user_id,
                {"type": "st_options_session", "topic": "st_options", "backtestJob": self._job_public(job)},
            )

    async def _fetch_perp_bars(self, underlying: str, *, end: datetime, days: int) -> list[OhlcBar]:
        start = end - timedelta(days=days)
        return await self._fetch_perp_bars_range(underlying, start, end)

    async def _fetch_perp_bars_range(
        self, underlying: str, start: datetime, end: datetime
    ) -> list[OhlcBar]:
        symbol = perp_symbol(underlying)
        raw: list[CandleBar] = await self._delta.fetch_candles(
            symbol,
            RESOLUTION,
            int(start.timestamp()),
            int(end.timestamp()),
        )
        return [
            OhlcBar(
                time=int(c.time),
                open=float(c.open),
                high=float(c.high),
                low=float(c.low),
                close=float(c.close),
                volume=float(c.volume or 0),
            )
            for c in raw
        ]

    async def _load_user(self, user_id: str) -> dict[str, Any]:
        doc = await self._db.app_users.find_one({"_id": ObjectId(user_id)})
        if not doc:
            raise http_error(401, "User not found")
        return {
            "id": str(doc["_id"]),
            "selectedAccountId": doc.get("selectedAccountId"),
        }

    async def _selected_account(self, user: dict[str, Any]) -> dict[str, Any]:
        if not user.get("selectedAccountId"):
            raise http_error(400, "Select a trading account first.")
        accounts = await self._accounts.list_raw_accounts(user)
        for account in accounts:
            if str(account.get("_id")) == str(user["selectedAccountId"]):
                return account
        raise http_error(404, "Account not found.")

    def _credentials(self, account: dict[str, Any]) -> tuple[str, str]:
        return (
            account.get("apiKey", ""),
            secret_crypto.decrypt(account.get("encryptedApiSecret", ""), settings.crypto_secret),
        )
