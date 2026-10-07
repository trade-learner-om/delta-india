import os

import pytest

from cryptobridge.mt5.client import LocalMt5Error, Mt5Client, _load_mt5
from cryptobridge.mt5.terminal_detection import find_running_terminal_paths, find_running_terminal_processes
from cryptobridge.services.journal_service import crypto_usd_pnl
from cryptobridge.services.mt5_account_service import _same_terminal_path
from cryptobridge.services.watchlist_service import filter_suggestions


class _Deal:
    def __init__(self, **kwargs):
        self._data = kwargs

    def _asdict(self):
        return dict(self._data)


class _Mt5Codes:
    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1
    DEAL_ENTRY_INOUT = 2
    DEAL_ENTRY_OUT_BY = 3
    DEAL_TYPE_BUY = 0
    DEAL_TYPE_SELL = 1


def _deal(**kwargs):
    base = {
        "type": 0,
        "position_id": 9,
        "time": 100,
        "price": 1.1,
        "volume": 0.1,
        "symbol": "EURUSD",
        "profit": 0,
        "commission": 0,
        "swap": 0,
        "fee": 0,
        "sl": 0,
        "tp": 0,
        "order": 1,
    }
    base.update(kwargs)
    return _Deal(**base)


def test_open_deal_entry_zero_pairs_with_the_close():
    rows = Mt5Client._closed_rows(
        _Mt5Codes(),
        [
            _deal(entry=0, ticket=1, time=100, price=1.1),
            _deal(entry=1, type=1, ticket=2, time=200, price=1.2, profit=10, commission=-1),
        ],
    )
    assert len(rows) == 1
    assert rows[0]["side"] == "BUY"
    assert rows[0]["entry"] == 1.1
    assert rows[0]["exit"] == 1.2
    assert rows[0]["netPnl"] == 9


def test_close_by_deal_counts_as_a_close():
    rows = Mt5Client._closed_rows(
        _Mt5Codes(),
        [
            _deal(entry=0, ticket=1, time=100),
            _deal(entry=3, type=1, ticket=3, time=300, price=1.3, profit=4),
        ],
    )
    assert len(rows) == 1
    assert rows[0]["exit"] == 1.3


def test_crypto_pnl_scales_contracts_into_usd():
    gross, net = crypto_usd_pnl("BUY", 100_000, 101_000, 10, 0.001, 1.5)
    assert gross == 10
    assert net == 8.5


def test_crypto_pnl_sell_is_the_opposite_move():
    gross, net = crypto_usd_pnl("SELL", 100_000, 99_000, 2, 0.001, 0)
    assert gross == 2
    assert net == 2


def test_suggestions_prefer_prefix_and_skip_owned():
    symbols = ["BTCUSD", "ETHUSD", "XBTUSD"]
    assert filter_suggestions(symbols, "bt", {"ETHUSD"}) == ["BTCUSD", "XBTUSD"]
    assert filter_suggestions(symbols, "b", set()) == []


@pytest.mark.skipif(os.name == "nt", reason="Windows lists real terminal processes")
def test_terminal_detection_is_empty_off_windows():
    assert find_running_terminal_processes() == []
    assert find_running_terminal_paths() == []


@pytest.mark.skipif(os.name == "nt", reason="Windows can import MetaTrader5")
def test_mt5_package_requires_the_windows_api_process():
    with pytest.raises(LocalMt5Error, match="not on Windows"):
        _load_mt5()


def test_shared_terminal_paths_match_after_normalizing():
    assert _same_terminal_path(r"C:\MT5\terminal64.exe", r"C:\MT5\terminal64.exe")
    assert not _same_terminal_path(r"C:\MT5-a\terminal64.exe", r"C:\MT5-b\terminal64.exe")
