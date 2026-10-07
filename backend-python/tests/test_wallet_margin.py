from cryptobridge.delta.wallet_margin import WalletMarginTracker, map_wallet_payload, resolve_wallet_margin
from cryptobridge.utils.signing import sign_delta_ws_auth


def test_sign_delta_ws_auth():
    secret = "test-secret"
    timestamp = "1542110948"
    assert sign_delta_ws_auth(secret, timestamp) == sign_delta_ws_auth(secret, timestamp)


def test_margin_tracker_applies_ws_update():
    tracker = WalletMarginTracker.empty()
    tracker.apply_margin_message(
        {
            "type": "margins",
            "asset_symbol": "INR",
            "available_balance": "84500.50",
            "balance": "90000",
        }
    )
    summary = tracker.summary()
    assert summary.asset_symbol == "INR"
    assert summary.available_balance == 84500.50
    assert summary.balance == 90000.0


def test_margin_tracker_uses_collateral_when_inr_available_is_zero():
    tracker = WalletMarginTracker.empty()
    tracker.apply_margin_message(
        {
            "asset_symbol": "INR",
            "available_balance": "0",
            "balance": "90000",
        }
    )
    tracker.apply_margin_message(
        {
            "asset_symbol": "USDT",
            "available_balance": "800",
            "balance": "800",
        }
    )
    summary = tracker.summary()
    assert summary.asset_symbol == "USDT"
    assert summary.available_balance == 800.0


def test_margin_tracker_uses_fno_robo_field():
    tracker = WalletMarginTracker.empty()
    tracker.apply_margin_message(
        {
            "type": "margins",
            "asset_symbol": "USD",
            "available_balance": "0",
            "available_balance_for_robo": "117.64",
            "balance": "117.64",
            "robo_trading_equity": "117.64",
        }
    )
    summary = tracker.summary()
    assert summary.available_balance == 117.64
    assert summary.asset_symbol == "USD"


def test_map_wallet_payload_uses_net_equity():
    summary = map_wallet_payload(
        {
            "meta": {"net_equity": "3200"},
            "result": [
                {"asset_symbol": "INR", "available_balance": "1000", "balance": "1000"},
            ],
        }
    )
    assert summary.available_balance == 3200.0


def test_resolve_wallet_margin_without_net_equity():
    summary = resolve_wallet_margin({"INR": (500.0, 600.0)})
    assert summary.available_balance == 500.0
    assert summary.asset_symbol == "INR"
