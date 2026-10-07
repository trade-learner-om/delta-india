import os

import pytest

from cryptobridge.mt5.terminal_detection import find_running_terminal_paths, find_running_terminal_processes
from cryptobridge.services.journal_service import crypto_usd_pnl
from cryptobridge.services.mt5_account_service import _same_terminal_path
from cryptobridge.services.watchlist_service import filter_suggestions


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


def test_shared_terminal_paths_match_after_normalizing():
    assert _same_terminal_path(r"C:\MT5\terminal64.exe", r"C:\MT5\terminal64.exe")
    assert not _same_terminal_path(r"C:\MT5-a\terminal64.exe", r"C:\MT5-b\terminal64.exe")
