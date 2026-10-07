from cryptobridge.utils.st_options_indicators import (
    OhlcBar,
    calculate_supertrend,
    compute_indicator_bars,
    ema_sma_seed,
    rma,
    true_range,
)


def _bars_from_closes(closes: list[float], start: int = 1_700_000_000) -> list[OhlcBar]:
    bars: list[OhlcBar] = []
    for i, close in enumerate(closes):
        # Synthetic OHLC with high/low around close for ATR.
        high = close + 1.0
        low = close - 1.0
        bars.append(
            OhlcBar(
                time=start + i * 3600,
                open=close,
                high=high,
                low=low,
                close=close,
            )
        )
    return bars


def test_true_range_with_gap():
    assert true_range(10, 8, None) == 2
    assert true_range(12, 10, 9) == 3  # max(2, 3, 1)


def test_rma_seeds_then_smooths():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = rma(values, 3)
    assert out[0] is None and out[1] is None
    assert out[2] == 2.0  # SMA(1,2,3)
    # next = (1/3)*4 + (2/3)*2 = 8/3
    assert abs(out[3] - 8 / 3) < 1e-9


def test_ema_sma_seed():
    closes = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = ema_sma_seed(closes, 3)
    assert out[0] is None and out[1] is None
    assert out[2] == 2.0
    alpha = 2.0 / 4.0
    expected = alpha * 4.0 + (1 - alpha) * 2.0
    assert abs(out[3] - expected) < 1e-9


def test_supertrend_initializes_and_flips():
    # Rising then falling series to force a direction change.
    closes = [100 + i for i in range(20)] + [118 - i for i in range(20)]
    bars = _bars_from_closes(closes)
    points = calculate_supertrend(bars, period=3, multiplier=1.0)
    warm = [p for p in points if p.direction is not None]
    assert len(warm) > 0
    assert warm[0].direction == -1  # first ATR bar red on upper
    assert any(p.flipped for p in warm)


def test_indicator_bars_track_colour_change_time():
    closes = [100 + i * 0.5 for i in range(30)] + [114 - i for i in range(30)]
    bars = _bars_from_closes(closes)
    inds = compute_indicator_bars(bars, st_period=3, st_multiplier=1.0, ema_length=3)
    flips = [b for b in inds if b.st.flipped]
    assert flips
    last = inds[-1]
    assert last.st_colour in {"green", "red"}
    assert last.st_colour_change_time is not None
