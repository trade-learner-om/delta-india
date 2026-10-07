"""Bar replay for Cascade Star. Candles are passed in; this module does not fetch them."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time, timezone
from typing import Sequence

from cryptobridge.utils.cascade_star_strategy import (
    DEFAULT_CHOP_LENGTH,
    DEFAULT_CHOP_MAX,
    DEFAULT_SESSION_END,
    DEFAULT_SESSION_START,
    DEFAULT_TARGET_R,
    RESOLUTION_SECONDS,
    evaluate_signal,
    parse_hhmm,
    pending_cancel_reason,
)
from cryptobridge.utils.risk_sizing import RiskSizingError, compute_position_size
from cryptobridge.utils.st_options_indicators import OhlcBar

DEFAULT_TAKER_RATE = 0.0005
GST_RATE = 0.18


@dataclass
class BacktestTrade:
    signal_time: int
    direction: str
    entry: float
    stop: float
    target: float
    r: float
    size: int
    chop: float | None
    fill_price: float | None = None
    fill_time: int | None = None
    exit_price: float | None = None
    exit_time: int | None = None
    exit_reason: str = ""
    gross_pnl: float = 0.0
    fee: float = 0.0
    pnl: float = 0.0

    def to_dict(self) -> dict:
        payload = asdict(self)
        return {
            "signalTime": payload["signal_time"],
            "direction": payload["direction"],
            "entry": payload["entry"],
            "stop": payload["stop"],
            "target": payload["target"],
            "r": payload["r"],
            "size": payload["size"],
            "chop": payload["chop"],
            "fillPrice": payload["fill_price"],
            "fillTime": payload["fill_time"],
            "exitPrice": payload["exit_price"],
            "exitTime": payload["exit_time"],
            "exitReason": payload["exit_reason"],
            "grossPnl": payload["gross_pnl"],
            "fee": payload["fee"],
            "pnl": payload["pnl"],
        }


@dataclass
class _Pending:
    signal_time: int
    direction: str
    entry: float
    stop: float
    target: float
    r: float
    size: int
    chop: float | None


@dataclass
class _Open:
    pending: _Pending
    fill_price: float
    fill_time: int


def simulate(
    bars: Sequence[OhlcBar],
    *,
    direction: str = "SHORT",
    tick_size: float | None = 0.5,
    contract_value: float = 0.001,
    taker_rate: float = DEFAULT_TAKER_RATE,
    sizing_mode: str = "max_risk",
    max_risk: float = 100.0,
    lots: int = 1,
    chop_length: int = DEFAULT_CHOP_LENGTH,
    chop_max: float = DEFAULT_CHOP_MAX,
    target_r: float = DEFAULT_TARGET_R,
    session_start: time | str = DEFAULT_SESSION_START,
    session_end: time | str = DEFAULT_SESSION_END,
    fill_timeout_bars: int = 5,
    window_start: int | None = None,
    window_end: int | None = None,
) -> dict:
    start_clock = session_start if isinstance(session_start, time) else parse_hhmm(str(session_start), DEFAULT_SESSION_START)
    end_clock = session_end if isinstance(session_end, time) else parse_hhmm(str(session_end), DEFAULT_SESSION_END)
    side = str(direction or "SHORT").upper()
    trades: list[BacktestTrade] = []
    pending: _Pending | None = None
    position: _Open | None = None

    for index, bar in enumerate(bars):
        if pending is not None:
            fill = _fill_price(bar, pending.entry, pending.direction)
            if fill is not None:
                position = _Open(pending=pending, fill_price=fill, fill_time=int(bar.time))
                pending = None
                closed = _exit_on_bar(position, bar, contract_value, taker_rate)
                if closed is not None:
                    trades.append(closed)
                    position = None
                continue
            reason = pending_cancel_reason(
                signal_bar_time=pending.signal_time,
                bars=bars[: index + 1],
                now=_bar_close(bar),
                fill_timeout_bars=fill_timeout_bars,
                session_start=start_clock,
                session_end=end_clock,
            )
            if reason:
                trades.append(_unfilled(pending, reason, int(bar.time)))
                pending = None
            continue

        if position is not None:
            closed = _exit_on_bar(position, bar, contract_value, taker_rate)
            if closed is not None:
                trades.append(closed)
                position = None
            continue

        if not _in_window(bar, window_start, window_end):
            continue
        decision = evaluate_signal(
            bars,
            index,
            direction=side,
            tick_size=tick_size,
            chop_length=chop_length,
            chop_max=chop_max,
            target_r=target_r,
            session_start=start_clock,
            session_end=end_clock,
        )
        if not decision.take or decision.levels is None:
            continue
        try:
            size = _size(sizing_mode, lots, max_risk, decision.levels.entry, decision.levels.stop, contract_value)
        except RiskSizingError:
            continue
        pending = _Pending(
            signal_time=int(bar.time),
            direction=side,
            entry=decision.levels.entry,
            stop=decision.levels.stop,
            target=decision.levels.target,
            r=decision.levels.r,
            size=size,
            chop=decision.chop,
        )

    if pending is not None and bars:
        trades.append(_unfilled(pending, "end_of_data", int(bars[-1].time)))
    if position is not None and bars:
        last = bars[-1]
        trades.append(
            _closed_trade(
                position,
                exit_price=float(last.close),
                exit_time=int(last.time),
                reason="end_of_data",
                contract_value=contract_value,
                taker_rate=taker_rate,
            )
        )

    return {"summary": _summary(trades), "trades": [trade.to_dict() for trade in trades]}


def _size(sizing_mode: str, lots: int, max_risk: float, entry: float, stop: float, contract_value: float) -> int:
    if str(sizing_mode).lower() == "lots":
        return max(1, int(lots))
    return max(1, int(compute_position_size(max_risk, entry, stop, contract_value)))


def _fill_price(bar: OhlcBar, entry: float, direction: str) -> float | None:
    if direction == "SHORT":
        if float(bar.open) <= entry:
            return float(bar.open)
        if float(bar.low) <= entry:
            return entry
        return None
    if float(bar.open) >= entry:
        return float(bar.open)
    if float(bar.high) >= entry:
        return entry
    return None


def _exit_on_bar(position: _Open, bar: OhlcBar, contract_value: float, taker_rate: float) -> BacktestTrade | None:
    pending = position.pending
    stop_hit, stop_price = _stop_touch(bar, pending.stop, pending.direction)
    target_hit, target_price = _target_touch(bar, pending.target, pending.direction)
    if stop_hit:
        return _closed_trade(position, stop_price, int(bar.time), "sl", contract_value, taker_rate)
    if target_hit:
        return _closed_trade(position, target_price, int(bar.time), "target", contract_value, taker_rate)
    return None


def _stop_touch(bar: OhlcBar, stop: float, direction: str) -> tuple[bool, float]:
    if direction == "SHORT":
        if float(bar.open) >= stop:
            return True, float(bar.open)
        if float(bar.high) >= stop:
            return True, stop
        return False, stop
    if float(bar.open) <= stop:
        return True, float(bar.open)
    if float(bar.low) <= stop:
        return True, stop
    return False, stop


def _target_touch(bar: OhlcBar, target: float, direction: str) -> tuple[bool, float]:
    if direction == "SHORT":
        if float(bar.open) <= target:
            return True, float(bar.open)
        if float(bar.low) <= target:
            return True, target
        return False, target
    if float(bar.open) >= target:
        return True, float(bar.open)
    if float(bar.high) >= target:
        return True, target
    return False, target


def _closed_trade(
    position: _Open,
    exit_price: float,
    exit_time: int,
    reason: str,
    contract_value: float,
    taker_rate: float,
) -> BacktestTrade:
    pending = position.pending
    gross = _gross(pending.direction, position.fill_price, exit_price, pending.size, contract_value)
    fee = _fee(position.fill_price, exit_price, pending.size, contract_value, taker_rate)
    return BacktestTrade(
        signal_time=pending.signal_time,
        direction=pending.direction,
        entry=pending.entry,
        stop=pending.stop,
        target=pending.target,
        r=pending.r,
        size=pending.size,
        chop=pending.chop,
        fill_price=position.fill_price,
        fill_time=position.fill_time,
        exit_price=exit_price,
        exit_time=exit_time,
        exit_reason=reason,
        gross_pnl=gross,
        fee=fee,
        pnl=gross - fee,
    )


def _unfilled(pending: _Pending, reason: str, exit_time: int) -> BacktestTrade:
    return BacktestTrade(
        signal_time=pending.signal_time,
        direction=pending.direction,
        entry=pending.entry,
        stop=pending.stop,
        target=pending.target,
        r=pending.r,
        size=pending.size,
        chop=pending.chop,
        exit_time=exit_time,
        exit_reason=reason,
    )


def _gross(direction: str, entry: float, exit_price: float, size: int, contract_value: float) -> float:
    move = (entry - exit_price) if direction == "SHORT" else (exit_price - entry)
    return move * size * contract_value


def _fee(entry: float, exit_price: float, size: int, contract_value: float, rate: float) -> float:
    entry_notional = contract_value * size * abs(entry)
    exit_notional = contract_value * size * abs(exit_price)
    return float(rate) * (entry_notional + exit_notional) * (1.0 + GST_RATE)


def _summary(trades: Sequence[BacktestTrade]) -> dict:
    filled = [trade for trade in trades if trade.fill_price is not None]
    wins = [trade for trade in filled if trade.pnl > 0]
    losses = [trade for trade in filled if trade.pnl <= 0]
    net = [trade.pnl for trade in filled]
    return {
        "trades": len(filled),
        "wins": len(wins),
        "losses": len(losses),
        "netPnl": sum(net),
        "maxWin": max(net) if net else 0.0,
        "maxLoss": min(net) if net else 0.0,
        "cancelled": sum(1 for trade in trades if trade.fill_price is None),
    }


def _bar_close(bar: OhlcBar) -> datetime:
    return datetime.fromtimestamp(int(bar.time) + RESOLUTION_SECONDS, tz=timezone.utc)


def _in_window(bar: OhlcBar, start: int | None, end: int | None) -> bool:
    close = int(bar.time) + RESOLUTION_SECONDS
    if start is not None and close < int(start):
        return False
    if end is not None and close > int(end):
        return False
    return True
