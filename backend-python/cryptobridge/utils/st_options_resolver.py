"""Strike / expiry waterfall for 1H ST Options.

Collect candidates across eligible expiries (T0 only until 10:30 IST; T1 always)
and the OTM3→ATM→ITM3 ladder. Prefer furthest OTM; ties go to later expiry.
Minimum premium % of perp is a hard floor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Literal, Mapping, Sequence
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

OptionSide = Literal["PUT", "CALL"]
Direction = Literal["LONG", "SHORT"]

STRIKE_STEP = {"BTC": 200.0, "ETH": 20.0}
CONTRACT_VALUE = {"BTC": 0.001, "ETH": 0.01}

# Same-day (T0) entries only at/before this IST clock time on the bar-close day.
T0_ENTRY_CUTOFF_IST = time(10, 30)
# Force square-off of same-day opens at this IST time.
FORCE_CLOSE_IST = time(17, 15)
# Daily options settle at this IST time.
SETTLEMENT_IST = time(17, 30)


@dataclass(frozen=True)
class ResolvedOption:
    underlying: str
    direction: Direction
    option_side: OptionSide
    strike: float
    expiry: date
    expiry_offset: int  # 0 = T0, 1 = T1
    itm_steps: int  # 0 = ATM or OTM … positive = ITM depth (legacy)
    symbol: str
    premium: float
    perp_price: float
    min_premium: float
    product_id: int | None = None
    contract_value: float | None = None
    moneyness_steps: int = 0  # positive = OTM, 0 = ATM, negative = ITM


def normalize_underlying(value: str) -> str:
    coin = str(value or "").strip().upper()
    if coin in {"BTC", "BTCUSD"}:
        return "BTC"
    if coin in {"ETH", "ETHUSD"}:
        return "ETH"
    raise ValueError(f"Unsupported underlying: {value}")


def perp_symbol(underlying: str) -> str:
    return f"{normalize_underlying(underlying)}USD"


def strike_step(underlying: str) -> float:
    return STRIKE_STEP[normalize_underlying(underlying)]


def contract_value_for(underlying: str) -> float:
    return CONTRACT_VALUE[normalize_underlying(underlying)]


def quantity_to_lots(underlying: str, quantity_coin: float) -> int:
    cv = contract_value_for(underlying)
    lots = int(round(float(quantity_coin) / cv))
    return max(1, lots)


def option_side_for_direction(direction: Direction) -> OptionSide:
    return "PUT" if direction == "LONG" else "CALL"


def ist_date_from_unix(ts: int) -> date:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(IST).date()


def ist_datetime_from_unix(ts: int) -> datetime:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(IST)


def expiry_dates_t0_t1(bar_close_unix: int) -> list[tuple[int, date]]:
    """T0 = IST calendar date of bar close; T1 = next day. Always both (prefetch)."""
    t0 = ist_date_from_unix(bar_close_unix)
    return [(0, t0), (1, t0 + timedelta(days=1))]


def eligible_expiries(bar_close_unix: int) -> list[tuple[int, date]]:
    """T1 always; T0 only when bar close IST time is at or before 10:30."""
    t0 = ist_date_from_unix(bar_close_unix)
    t1 = t0 + timedelta(days=1)
    close_ist = ist_datetime_from_unix(bar_close_unix)
    out: list[tuple[int, date]] = []
    if close_ist.time() <= T0_ENTRY_CUTOFF_IST:
        out.append((0, t0))
    out.append((1, t1))
    return out


def snap_atm(spot: float, step: float) -> float:
    if step <= 0:
        raise ValueError("step must be > 0")
    return round(spot / step) * step


def strike_band_min_max(closes: list[float], underlying: str, depth: int = 3) -> set[float]:
    """All grid strikes from (min ATM − depth) through (max ATM + depth)."""
    if not closes:
        return set()
    coin = normalize_underlying(underlying)
    step = strike_step(coin)
    lo = snap_atm(min(closes), step) - depth * step
    hi = snap_atm(max(closes), step) + depth * step
    band: set[float] = set()
    strike = lo
    while strike <= hi + step * 0.5:
        if strike > 0:
            band.add(float(strike))
        strike += step
    return band


def strike_in_band(strike: float, band: set[float]) -> bool:
    for value in band:
        if abs(float(strike) - float(value)) < 1e-6:
            return True
    return False


def itm_strikes(spot: float, option_side: OptionSide, underlying: str, depth: int = 3) -> list[tuple[int, float]]:
    """Legacy ATM→ITM ladder. Prefer strike_ladder for new code."""
    step = strike_step(underlying)
    atm = snap_atm(spot, step)
    out: list[tuple[int, float]] = []
    for n in range(0, depth + 1):
        if option_side == "PUT":
            strike = atm + n * step
        else:
            strike = atm - n * step
        if strike <= 0:
            continue
        out.append((n, strike))
    return out


def strike_ladder(
    spot: float,
    option_side: OptionSide,
    underlying: str,
    *,
    otm_depth: int = 3,
    itm_depth: int = 3,
) -> list[tuple[int, float]]:
    """
    Return (moneyness_steps, strike) ordered OTM3 → … → ATM → … → ITM3.
    Positive moneyness_steps = OTM, 0 = ATM, negative = ITM.
    PUT OTM = atm - n*step; CALL OTM = atm + n*step.
    """
    step = strike_step(underlying)
    atm = snap_atm(spot, step)
    out: list[tuple[int, float]] = []
    for n in range(otm_depth, 0, -1):
        if option_side == "PUT":
            strike = atm - n * step
        else:
            strike = atm + n * step
        if strike > 0:
            out.append((n, float(strike)))
    out.append((0, float(atm)))
    for n in range(1, itm_depth + 1):
        if option_side == "PUT":
            strike = atm + n * step
        else:
            strike = atm - n * step
        if strike > 0:
            out.append((-n, float(strike)))
    return out


def delta_option_symbol(option_side: OptionSide, underlying: str, strike: float, expiry: date) -> str:
    coin = normalize_underlying(underlying)
    prefix = "P" if option_side == "PUT" else "C"
    strike_int = int(strike) if float(strike).is_integer() else strike
    suffix = expiry.strftime("%d%m%y")
    return f"{prefix}-{coin}-{strike_int}-{suffix}"


def parse_option_symbol_expiry(symbol: str) -> date | None:
    """Parse DDMMYY suffix from Delta option symbols like C-BTC-65000-240726."""
    parts = str(symbol or "").strip().upper().split("-")
    if len(parts) < 4:
        return None
    suffix = parts[-1]
    if len(suffix) != 6 or not suffix.isdigit():
        return None
    day = int(suffix[0:2])
    month = int(suffix[2:4])
    year = 2000 + int(suffix[4:6])
    try:
        return date(year, month, day)
    except ValueError:
        return None


def product_expiry_date(product: object) -> date | None:
    """Best-effort expiry day from symbol suffix or settlement/expiry field."""
    symbol = str(getattr(product, "symbol", "") or "")
    parsed = parse_option_symbol_expiry(symbol)
    if parsed is not None:
        return parsed
    raw = str(getattr(product, "expiry", "") or "")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(IST).date()
    except ValueError:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None


def product_matches_expiry(product: object, expected: date) -> bool:
    actual = product_expiry_date(product)
    return actual is not None and actual == expected


def expiry_iso(expiry: date) -> str:
    return expiry.isoformat()


def premium_meets_min(premium: float | None, perp_price: float, min_premium_pct: float) -> bool:
    if premium is None or premium <= 0 or perp_price <= 0:
        return False
    return float(premium) >= (perp_price * float(min_premium_pct) / 100.0)


def premium_meets_abs(premium: float | None, min_premium_abs: float) -> bool:
    if premium is None or premium <= 0:
        return False
    return float(premium) >= float(min_premium_abs)


StrikeSelectMode = Literal["fixed", "min_pct", "supertrend", "min_abs"]
# Fixed-mode same-day expiry only when bar close IST is before this clock time.
FIXED_SAME_DAY_CUTOFF_IST = time(5, 30)


def parse_strike_type(strike_type: str) -> int:
    """Return moneyness_steps: +N OTM, 0 ATM, -N ITM."""
    raw = str(strike_type or "ATM").strip().upper()
    if raw == "ATM":
        return 0
    if raw.startswith("OTM") and raw[3:].isdigit():
        n = int(raw[3:])
        if 1 <= n <= 10:
            return n
    if raw.startswith("ITM") and raw[3:].isdigit():
        n = int(raw[3:])
        if 1 <= n <= 10:
            return -n
    raise ValueError(f"Invalid strikeType: {strike_type}")


def strike_from_moneyness(
    spot: float,
    option_side: OptionSide,
    underlying: str,
    moneyness_steps: int,
) -> float:
    step = strike_step(underlying)
    atm = snap_atm(spot, step)
    n = int(moneyness_steps)
    if n == 0:
        return float(atm)
    if option_side == "PUT":
        # +OTM = below ATM; -ITM = above ATM
        return float(atm - n * step)
    # CALL: +OTM = above ATM; -ITM = below ATM
    return float(atm + n * step)


def fixed_mode_expiry(bar_close_unix: int) -> tuple[int, date]:
    """Same-day (T0) if bar-close IST < 05:30, else next day (T+1)."""
    t0 = ist_date_from_unix(bar_close_unix)
    close_ist = ist_datetime_from_unix(bar_close_unix)
    if close_ist.time() < FIXED_SAME_DAY_CUTOFF_IST:
        return 0, t0
    return 1, t0 + timedelta(days=1)


def _candidate(
    *,
    coin: str,
    direction: Direction,
    side: OptionSide,
    strike: float,
    expiry: date,
    expiry_offset: int,
    moneyness_steps: int,
    premium: float,
    perp_price: float,
    min_premium: float,
) -> ResolvedOption:
    return ResolvedOption(
        underlying=coin,
        direction=direction,
        option_side=side,
        strike=float(strike),
        expiry=expiry,
        expiry_offset=expiry_offset,
        itm_steps=max(0, -int(moneyness_steps)),
        moneyness_steps=int(moneyness_steps),
        symbol=delta_option_symbol(side, coin, strike, expiry),
        premium=float(premium),
        perp_price=float(perp_price),
        min_premium=float(min_premium),
        contract_value=contract_value_for(coin),
    )


def resolve_fixed_moneyness(
    *,
    underlying: str,
    direction: Direction,
    perp_price: float,
    bar_close_unix: int,
    strike_type: str,
    premium_lookup: Callable[[str, date, float, OptionSide], float | None],
) -> ResolvedOption | None:
    """Exact moneyness on auto expiry (before 05:30 IST → T0, else T+1)."""
    coin = normalize_underlying(underlying)
    side = option_side_for_direction(direction)
    steps = parse_strike_type(strike_type)
    strike = strike_from_moneyness(perp_price, side, coin, steps)
    if strike <= 0:
        return None
    offset, expiry = fixed_mode_expiry(bar_close_unix)
    symbol = delta_option_symbol(side, coin, strike, expiry)
    premium = premium_lookup(symbol, expiry, strike, side)
    if premium is None or premium <= 0:
        return None
    return _candidate(
        coin=coin,
        direction=direction,
        side=side,
        strike=strike,
        expiry=expiry,
        expiry_offset=offset,
        moneyness_steps=steps,
        premium=float(premium),
        perp_price=perp_price,
        min_premium=0.0,
    )


def resolve_supertrend_atm(
    *,
    underlying: str,
    direction: Direction,
    st_line: float,
    perp_price: float,
    bar_close_unix: int,
    premium_lookup: Callable[[str, date, float, OptionSide], float | None],
) -> ResolvedOption | None:
    """ATM strike snapped to SuperTrend line; prefer T0 then T1 among eligible."""
    coin = normalize_underlying(underlying)
    side = option_side_for_direction(direction)
    strike = float(snap_atm(float(st_line), strike_step(coin)))
    if strike <= 0:
        return None
    for offset, expiry in sorted(eligible_expiries(bar_close_unix), key=lambda x: x[0]):
        symbol = delta_option_symbol(side, coin, strike, expiry)
        premium = premium_lookup(symbol, expiry, strike, side)
        if premium is None or premium <= 0:
            continue
        return _candidate(
            coin=coin,
            direction=direction,
            side=side,
            strike=strike,
            expiry=expiry,
            expiry_offset=offset,
            moneyness_steps=0,
            premium=float(premium),
            perp_price=perp_price,
            min_premium=0.0,
        )
    return None


def collect_option_waterfall(
    *,
    underlying: str,
    direction: Direction,
    perp_price: float,
    bar_close_unix: int,
    min_premium_pct: float = 5.0,
    min_premium_abs: float | None = None,
    premium_lookup: Callable[[str, date, float, OptionSide], float | None],
    depth: int = 3,
) -> list[ResolvedOption]:
    """All strikes that clear the premium floor across eligible expiries and the ladder."""
    coin = normalize_underlying(underlying)
    side = option_side_for_direction(direction)
    use_abs = min_premium_abs is not None
    min_premium = float(min_premium_abs) if use_abs else perp_price * float(min_premium_pct) / 100.0
    ladder = strike_ladder(perp_price, side, coin, otm_depth=depth, itm_depth=depth)

    candidates: list[ResolvedOption] = []
    for offset, expiry in eligible_expiries(bar_close_unix):
        for moneyness_steps, strike in ladder:
            symbol = delta_option_symbol(side, coin, strike, expiry)
            premium = premium_lookup(symbol, expiry, strike, side)
            if use_abs:
                if not premium_meets_abs(premium, float(min_premium_abs)):
                    continue
            elif not premium_meets_min(premium, perp_price, min_premium_pct):
                continue
            candidates.append(
                _candidate(
                    coin=coin,
                    direction=direction,
                    side=side,
                    strike=float(strike),
                    expiry=expiry,
                    expiry_offset=offset,
                    moneyness_steps=int(moneyness_steps),
                    premium=float(premium or 0.0),
                    perp_price=perp_price,
                    min_premium=min_premium,
                )
            )
    return candidates


def pick_above_average_volume(
    candidates: Sequence[ResolvedOption],
    volume_by_symbol: Mapping[str, float | None],
) -> list[ResolvedOption]:
    """Keep strikes whose ticker volume is strictly above the band average.

    Missing or invalid volumes count as 0 in the average. All-zero / empty → [].
    """
    if not candidates:
        return []
    volumes: list[float] = []
    for candidate in candidates:
        raw = volume_by_symbol.get(candidate.symbol)
        try:
            vol = float(raw) if raw is not None else 0.0
        except (TypeError, ValueError):
            vol = 0.0
        volumes.append(max(0.0, vol))
    avg = sum(volumes) / len(volumes)
    if avg <= 0:
        return []
    return [c for c, vol in zip(candidates, volumes) if vol > avg]


def resolve_option_waterfall(
    *,
    underlying: str,
    direction: Direction,
    perp_price: float,
    bar_close_unix: int,
    min_premium_pct: float = 5.0,
    min_premium_abs: float | None = None,
    premium_lookup: Callable[[str, date, float, OptionSide], float | None],
    depth: int = 3,
) -> ResolvedOption | None:
    """
    Collect all candidates that clear the min premium floor across eligible
    expiries and the OTM→ITM ladder; pick furthest OTM, then later expiry.

    When ``min_premium_abs`` is set, use an absolute premium floor instead of %.
    """
    candidates = collect_option_waterfall(
        underlying=underlying,
        direction=direction,
        perp_price=perp_price,
        bar_close_unix=bar_close_unix,
        min_premium_pct=min_premium_pct,
        min_premium_abs=min_premium_abs,
        premium_lookup=premium_lookup,
        depth=depth,
    )
    if not candidates:
        return None
    candidates.sort(key=lambda c: (-c.moneyness_steps, -c.expiry_offset))
    return candidates[0]


def resolve_backtest_strike(
    *,
    mode: StrikeSelectMode | str,
    underlying: str,
    direction: Direction,
    perp_price: float,
    bar_close_unix: int,
    premium_lookup: Callable[[str, date, float, OptionSide], float | None],
    min_premium_pct: float = 5.0,
    min_premium_abs: float = 0.0,
    strike_type: str = "ATM",
    st_line: float | None = None,
) -> ResolvedOption | None:
    """Dispatch backtest-only strike selection modes."""
    key = str(mode or "min_pct").strip().lower()
    if key == "fixed":
        return resolve_fixed_moneyness(
            underlying=underlying,
            direction=direction,
            perp_price=perp_price,
            bar_close_unix=bar_close_unix,
            strike_type=strike_type,
            premium_lookup=premium_lookup,
        )
    if key == "supertrend":
        if st_line is None:
            return None
        return resolve_supertrend_atm(
            underlying=underlying,
            direction=direction,
            st_line=float(st_line),
            perp_price=perp_price,
            bar_close_unix=bar_close_unix,
            premium_lookup=premium_lookup,
        )
    if key == "min_abs":
        return resolve_option_waterfall(
            underlying=underlying,
            direction=direction,
            perp_price=perp_price,
            bar_close_unix=bar_close_unix,
            min_premium_abs=float(min_premium_abs),
            premium_lookup=premium_lookup,
            depth=10,
        )
    return resolve_option_waterfall(
        underlying=underlying,
        direction=direction,
        perp_price=perp_price,
        bar_close_unix=bar_close_unix,
        min_premium_pct=min_premium_pct,
        premium_lookup=premium_lookup,
        depth=3,
    )


def settlement_intrinsic(
    *,
    option_side: OptionSide,
    strike: float,
    settlement_spot: float,
) -> float:
    """Cash settlement value of a long option at expiry (short pays this)."""
    if option_side == "PUT":
        return max(0.0, float(strike) - float(settlement_spot))
    return max(0.0, float(settlement_spot) - float(strike))


def force_close_cutoff_unix(expiry_day: date) -> int:
    """Unix timestamp of FORCE_CLOSE_IST on the expiry calendar day (IST)."""
    dt = datetime(
        expiry_day.year,
        expiry_day.month,
        expiry_day.day,
        FORCE_CLOSE_IST.hour,
        FORCE_CLOSE_IST.minute,
        tzinfo=IST,
    )
    return int(dt.timestamp())


def settlement_unix(expiry_day: date) -> int:
    """Unix timestamp of SETTLEMENT_IST on the expiry calendar day (IST)."""
    dt = datetime(
        expiry_day.year,
        expiry_day.month,
        expiry_day.day,
        SETTLEMENT_IST.hour,
        SETTLEMENT_IST.minute,
        tzinfo=IST,
    )
    return int(dt.timestamp())


def pick_product_premium(
    products: Sequence[object],
    *,
    strike: float,
    option_side: OptionSide,
    expiry: date,
    premium_attr: str = "mark_price",
) -> tuple[object | None, float | None]:
    """Match a ProductSummary-like object by strike / type / expiry day."""
    for product in products:
        p_strike = getattr(product, "strike_price", None)
        if p_strike is None:
            continue
        if abs(float(p_strike) - float(strike)) > 1e-6:
            continue
        ctype = str(getattr(product, "contract_type", "") or "").lower()
        symbol = str(getattr(product, "symbol", "") or "").upper()
        is_put = "put" in ctype or symbol.startswith("P-")
        is_call = "call" in ctype or symbol.startswith("C-")
        if option_side == "PUT" and not is_put:
            continue
        if option_side == "CALL" and not is_call:
            continue
        exp_raw = str(getattr(product, "expiry", "") or "")
        if exp_raw:
            try:
                exp_day = datetime.fromisoformat(exp_raw.replace("Z", "+00:00")).astimezone(IST).date()
            except ValueError:
                try:
                    exp_day = date.fromisoformat(exp_raw[:10])
                except ValueError:
                    exp_day = None
            if exp_day is not None and exp_day != expiry:
                continue
        premium = getattr(product, premium_attr, None)
        if premium is None:
            premium = getattr(product, "close_price", None)
        if premium is None:
            continue
        return product, float(premium)
    return None, None


def bar_close_unix(bar_open_unix: int, resolution_seconds: int = 3600) -> int:
    return int(bar_open_unix) + int(resolution_seconds)


def format_ist(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(IST).strftime("%Y-%m-%d %H:%M IST")
