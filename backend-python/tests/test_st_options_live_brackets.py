from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from cryptobridge.delta.rest_client import BracketLegs, ProductSummary

try:
    from cryptobridge.services.st_options_service import (
        STATUS_OPEN,
        STATUS_PENDING_ENTRY,
        BracketCancelResult,
        ENTRY_CANCEL_RETRIES,
        StOptionsService,
        _default_config,
        _is_limit_entry_filled,
        _order_filled_size,
        config_to_view,
    )
except ImportError as exc:
    if "cannot import name 'SON' from 'bson'" in str(exc):
        pytest.skip(
            "Local bson/pymongo packages conflict; service tests require the project environment",
            allow_module_level=True,
        )
    raise


def _service():
    service = object.__new__(StOptionsService)
    service._delta = SimpleNamespace()
    service._trades = SimpleNamespace(update_one=AsyncMock())
    service._push_activity = Mock()
    service._indicator_snapshot = AsyncMock(return_value=None)
    return service


def _product():
    return ProductSummary(
        symbol="C-BTC-70000-270726",
        product_id=123,
        contract_value=0.001,
        tick_size=0.1,
        contract_unit_currency="BTC",
        quoting_asset="USD",
    )


def test_live_config_defaults_include_editable_brackets():
    view = config_to_view(_default_config("user-1"))
    assert view["stopLossPct"] == 105.0
    assert view["takeProfitPct"] == 95.0
    assert view["pairHedgeDecayPct"] == 0.0


@pytest.mark.asyncio
async def test_attach_bracket_stores_broker_leg_ids():
    service = _service()
    service._delta.place_position_bracket = AsyncMock()
    empty = BracketLegs()
    found = BracketLegs(stop_loss_order_id=11, take_profit_order_id=12)
    service._delta.find_bracket_legs = AsyncMock(side_effect=[empty, empty, found])
    service._delta.fetch_order = AsyncMock(return_value=None)
    doc = {
        "_id": "trade-1",
        "status": STATUS_OPEN,
        "optionSymbol": "C-BTC-70000-270726",
        "stopPremium": 205,
        "targetPremium": 5,
    }

    attached = await service._attach_bracket_protection(
        "user-1", doc, _product(), "key", "secret"
    )

    assert attached is True
    assert doc["stopOrderId"] == 11
    assert doc["takeProfitOrderId"] == 12
    service._delta.place_position_bracket.assert_awaited_once()
    update = service._trades.update_one.await_args.args[1]["$set"]
    assert update["stopOrderId"] == 11
    assert update["takeProfitOrderId"] == 12
    assert update["bracketAttached"] is True


@pytest.mark.asyncio
async def test_attach_bracket_links_existing_broker_legs_without_place():
    service = _service()
    service._delta.place_position_bracket = AsyncMock()
    service._delta.find_bracket_legs = AsyncMock(
        return_value=BracketLegs(stop_loss_order_id=21, take_profit_order_id=22)
    )
    service._delta.fetch_order = AsyncMock(
        side_effect=[
            SimpleNamespace(stop_price=640.0),
            SimpleNamespace(stop_price=220.0),
        ]
    )
    doc = {
        "_id": "trade-2",
        "status": STATUS_OPEN,
        "optionSymbol": "C-BTC-63800-120826",
        "stopPremium": 600,
        "targetPremium": 200,
    }

    attached = await service._attach_bracket_protection(
        "user-1", doc, _product(), "key", "secret"
    )

    assert attached is True
    service._delta.place_position_bracket.assert_not_awaited()
    assert doc["stopOrderId"] == 21
    assert doc["takeProfitOrderId"] == 22
    assert doc["stopPremium"] == 640.0
    assert doc["targetPremium"] == 220.0
    assert service._push_activity.call_args.kwargs["level"] == "success"


@pytest.mark.asyncio
async def test_attach_bracket_recovers_when_place_fails_but_legs_exist():
    service = _service()
    service._delta.place_position_bracket = AsyncMock(side_effect=RuntimeError("already exists"))
    empty = BracketLegs()
    found = BracketLegs(stop_loss_order_id=31, take_profit_order_id=32)
    # First discover empty → place fails → recover discover finds legs
    service._delta.find_bracket_legs = AsyncMock(side_effect=[empty, empty, found, found])
    service._delta.fetch_order = AsyncMock(return_value=None)
    doc = {
        "_id": "trade-3",
        "status": STATUS_OPEN,
        "optionSymbol": "C-BTC-63800-120826",
        "stopPremium": 600,
        "targetPremium": 200,
    }

    attached = await service._attach_bracket_protection(
        "user-1", doc, _product(), "key", "secret"
    )

    assert attached is True
    assert doc["stopOrderId"] == 31
    assert doc["takeProfitOrderId"] == 32
    service._delta.place_position_bracket.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_brackets_cancels_pending_legs_before_exit():
    service = _service()
    service._trade_credentials = AsyncMock(return_value=("key", "secret"))
    service._delta.fetch_order = AsyncMock(
        return_value=SimpleNamespace(status="PENDING")
    )
    service._delta.cancel_order = AsyncMock()
    service._delta.find_bracket_legs = AsyncMock(
        return_value=BracketLegs(stop_loss_order_id=11, take_profit_order_id=12)
    )
    doc = {
        "_id": "trade-1",
        "optionSymbol": "C-BTC-70000-270726",
        "stopOrderId": 11,
        "takeProfitOrderId": 12,
        "bracketAttached": True,
    }

    cancelled = await service._cancel_bracket_legs("user-1", doc)

    assert cancelled.ok is True
    assert cancelled.cleared is True
    assert doc.get("bracketAttached") is False
    assert [call.args[2] for call in service._delta.cancel_order.await_args_list] == [
        11,
        12,
    ]


@pytest.mark.asyncio
async def test_cancel_failure_keeps_bracket_ids():
    service = _service()
    service._trade_credentials = AsyncMock(return_value=("key", "secret"))
    service._delta.fetch_order = AsyncMock(
        return_value=SimpleNamespace(status="PENDING")
    )
    service._delta.cancel_order = AsyncMock(side_effect=RuntimeError("busy"))
    service._delta.find_bracket_legs = AsyncMock(
        return_value=BracketLegs(stop_loss_order_id=11, take_profit_order_id=12)
    )
    doc = {
        "_id": "trade-1",
        "optionSymbol": "C-BTC-70000-270726",
        "stopOrderId": 11,
        "takeProfitOrderId": 12,
        "bracketAttached": True,
    }

    cancelled = await service._cancel_bracket_legs("user-1", doc)

    assert cancelled.ok is False
    assert cancelled.cleared is False
    assert doc["stopOrderId"] == 11
    assert doc["takeProfitOrderId"] == 12
    assert doc["bracketAttached"] is True


@pytest.mark.asyncio
async def test_cancel_detects_already_filled_stop():
    service = _service()
    service._trade_credentials = AsyncMock(return_value=("key", "secret"))

    async def fetch_order(_key, _secret, order_id):
        if order_id == 11:
            return SimpleNamespace(id=11, status="FILLED", average_fill_price=210)
        return SimpleNamespace(id=12, status="PENDING", average_fill_price=None)

    service._delta.fetch_order = AsyncMock(side_effect=fetch_order)
    service._delta.cancel_order = AsyncMock()
    service._delta.find_bracket_legs = AsyncMock(
        return_value=BracketLegs(stop_loss_order_id=11, take_profit_order_id=12)
    )
    doc = {
        "_id": "trade-1",
        "optionSymbol": "C-BTC-70000-270726",
        "stopOrderId": 11,
        "takeProfitOrderId": 12,
        "bracketAttached": True,
    }

    cancelled = await service._cancel_bracket_legs("user-1", doc)

    assert cancelled.ok is True
    assert cancelled.filled_reason == "stop_loss"
    assert cancelled.filled_order.id == 11
    service._delta.cancel_order.assert_awaited_once_with("key", "secret", 12)


@pytest.mark.asyncio
async def test_st_flip_cancels_brackets_before_market_reduce():
    service = _service()
    events = []
    service._market = SimpleNamespace(latest_tickers={})
    service._reconcile_broker_bracket = AsyncMock(return_value="protected")

    async def cancel_brackets(*_args):
        events.append("cancel")
        return BracketCancelResult(ok=True, cleared=True)

    async def market_reduce(*_args):
        events.append("reduce")
        return SimpleNamespace(id=99, average_fill_price=120)

    service._cancel_bracket_legs = AsyncMock(side_effect=cancel_brackets)
    service._trade_credentials = AsyncMock(return_value=("key", "secret"))
    service._delta.fetch_product = AsyncMock(return_value=_product())
    service._delta.place_market_reduce = AsyncMock(side_effect=market_reduce)
    service._maybe_reenter_after_close = AsyncMock()
    doc = {
        "_id": "trade-1",
        "userId": "user-1",
        "accountId": "account-1",
        "direction": "SHORT",
        "status": STATUS_OPEN,
        "underlying": "BTC",
        "optionSymbol": "C-BTC-70000-270726",
        "premiumReceived": 100,
        "contractValue": 0.001,
        "lots": 1,
        "stopOrderId": 11,
        "takeProfitOrderId": 12,
        "bracketAttached": True,
    }

    closed = await service._close_live_trade(
        "user-1",
        doc,
        reason="st_flip",
        exit_premium=120,
    )

    assert closed is True
    assert events == ["cancel", "reduce"]


@pytest.mark.asyncio
async def test_st_flip_records_fill_instead_of_reduce_when_sl_already_hit():
    service = _service()
    service._market = SimpleNamespace(latest_tickers={})
    service._reconcile_broker_bracket = AsyncMock(return_value="protected")
    service._cancel_bracket_legs = AsyncMock(
        return_value=BracketCancelResult(
            ok=True,
            filled_reason="stop_loss",
            filled_order=SimpleNamespace(id=11, average_fill_price=210, status="CLOSED"),
            cleared=True,
        )
    )
    service._record_broker_bracket_exit = AsyncMock()
    service._delta.place_market_reduce = AsyncMock()
    doc = {
        "_id": "trade-1",
        "optionSymbol": "C-BTC-70000-270726",
        "premiumReceived": 100,
        "stopPremium": 205,
        "targetPremium": 5,
        "stopOrderId": 11,
        "takeProfitOrderId": 12,
        "bracketAttached": True,
        "lots": 1,
        "contractValue": 0.001,
        "underlying": "BTC",
    }

    closed = await service._close_live_trade(
        "user-1",
        doc,
        reason="st_flip",
        exit_premium=120,
    )

    assert closed is True
    service._delta.place_market_reduce.assert_not_awaited()
    service._record_broker_bracket_exit.assert_awaited_once()
    assert service._record_broker_bracket_exit.await_args.kwargs["reason"] == "stop_loss"


@pytest.mark.asyncio
async def test_st_flip_blocks_reduce_when_cancel_fails():
    service = _service()
    service._market = SimpleNamespace(latest_tickers={})
    service._reconcile_broker_bracket = AsyncMock(return_value="protected")
    service._cancel_bracket_legs = AsyncMock(
        return_value=BracketCancelResult(ok=False, cleared=False)
    )
    service._delta.place_market_reduce = AsyncMock()
    doc = {
        "_id": "trade-1",
        "optionSymbol": "C-BTC-70000-270726",
        "premiumReceived": 100,
        "lots": 1,
        "contractValue": 0.001,
        "underlying": "BTC",
        "direction": "SHORT",
        "stopOrderId": 11,
        "takeProfitOrderId": 12,
        "bracketAttached": True,
    }

    closed = await service._close_live_trade(
        "user-1",
        doc,
        reason="st_flip",
        exit_premium=120,
    )

    assert closed is False
    service._delta.place_market_reduce.assert_not_awaited()
    update = service._trades.update_one.await_args.args[1]["$set"]
    assert update["closeError"] == "bracket_cancel_failed"


@pytest.mark.asyncio
async def test_reconcile_target_fill_records_exit_without_market_reduce():
    service = _service()
    service._trade_credentials = AsyncMock(return_value=("key", "secret"))
    service._record_broker_bracket_exit = AsyncMock()
    service._delta.find_bracket_legs = AsyncMock(
        return_value=BracketLegs(stop_loss_order_id=11, take_profit_order_id=12)
    )

    async def fetch_order(_key, _secret, order_id):
        if order_id == 12:
            return SimpleNamespace(
                id=12,
                status="FILLED",
                average_fill_price=4.5,
            )
        return SimpleNamespace(id=11, status="PENDING", average_fill_price=None)

    service._delta.fetch_order = AsyncMock(side_effect=fetch_order)
    service._delta.cancel_order = AsyncMock()
    doc = {
        "_id": "trade-1",
        "optionSymbol": "C-BTC-70000-270726",
        "premiumReceived": 100,
        "livePremium": 5,
        "stopPremium": 205,
        "targetPremium": 5,
        "stopOrderId": 11,
        "takeProfitOrderId": 12,
        "bracketAttached": True,
    }

    state = await service._reconcile_broker_bracket("user-1", doc)

    assert state == "closed"
    service._record_broker_bracket_exit.assert_awaited_once_with(
        "user-1",
        doc,
        reason="take_profit",
        exit_price=4.5,
        close_order_id=12,
    )


@pytest.mark.asyncio
async def test_reconcile_missing_ids_falls_back_to_soft_monitoring():
    service = _service()
    service._trade_credentials = AsyncMock(return_value=("key", "secret"))
    service._delta.find_bracket_legs = AsyncMock(
        return_value=BracketLegs(stop_loss_order_id=None, take_profit_order_id=None)
    )
    doc = {
        "_id": "trade-1",
        "optionSymbol": "C-BTC-70000-270726",
        "bracketAttached": True,
    }

    state = await service._reconcile_broker_bracket("user-1", doc)

    assert state == "fallback"
    assert doc.get("bracketAttached") is False


class _AsyncCursor:
    def __init__(self, rows):
        self._rows = rows

    def __aiter__(self):
        self._iterator = iter(self._rows)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bracket_state", "close_count"),
    [("protected", 0), ("fallback", 1)],
)
async def test_soft_brackets_only_run_without_broker_protection(
    bracket_state,
    close_count,
):
    service = _service()
    doc = {
        "_id": "trade-1",
        "optionSymbol": "C-BTC-70000-270726",
        "premiumReceived": 100,
        "stopLossPct": 50,
        "takeProfitPct": 60,
    }
    service._trades.find = Mock(return_value=_AsyncCursor([doc]))
    service._market = SimpleNamespace(
        ensure_symbols=AsyncMock(),
        latest_tickers={
            "C-BTC-70000-270726": SimpleNamespace(
                mark_price=160,
                last_price=None,
                bid=None,
                ask=None,
            )
        },
    )
    service._reconcile_broker_bracket = AsyncMock(return_value=bracket_state)
    service._close_live_trade = AsyncMock(return_value=True)
    service._open_live_hedge = AsyncMock(return_value=None)
    service.get_config = AsyncMock(return_value=config_to_view(_default_config("user-1")))

    await service._manage_open_premiums("user-1", config_to_view(_default_config("user-1")))

    assert service._close_live_trade.await_count == close_count
    if close_count:
        assert service._close_live_trade.await_args.kwargs["reason"] == "stop_loss"
        assert service._close_live_trade.await_args.kwargs["exit_premium"] == 150.0
    service._open_live_hedge.assert_not_awaited()


@pytest.mark.asyncio
async def test_manage_opens_decay_hedge_when_armed():
    service = _service()
    doc = {
        "_id": "trade-1",
        "optionSymbol": "P-BTC-70000-270726",
        "optionSide": "PUT",
        "premiumReceived": 100,
        "stopLossPct": 105,
        "takeProfitPct": 95,
        "hedgeStatus": "none",
        "lots": 2,
        "contractValue": 0.001,
        "underlying": "BTC",
    }
    opened = {**doc, "hedgeStatus": "open", "hedgeSymbol": "C-BTC-70000-270726", "hedgePremiumReceived": 80}
    service._trades.find = Mock(return_value=_AsyncCursor([doc]))
    service._market = SimpleNamespace(
        ensure_symbols=AsyncMock(),
        latest_tickers={
            "P-BTC-70000-270726": SimpleNamespace(
                mark_price=55, last_price=None, bid=None, ask=None
            )
        },
    )
    service._maybe_move_sl_to_breakeven = AsyncMock(side_effect=lambda _u, d, _p: d)
    service._open_live_hedge = AsyncMock(return_value=opened)
    service._reconcile_broker_bracket = AsyncMock(return_value="protected")
    service._close_live_trade = AsyncMock(return_value=True)
    config = config_to_view(_default_config("user-1"))
    config["pairHedgeDecayPct"] = 40.0
    config["maxRisk"] = 100.0

    await service._manage_open_premiums("user-1", config)

    service._open_live_hedge.assert_awaited_once()


@pytest.mark.asyncio
async def test_manage_skips_hedge_when_decay_pct_zero():
    service = _service()
    doc = {
        "_id": "trade-1",
        "optionSymbol": "P-BTC-70000-270726",
        "premiumReceived": 100,
        "stopLossPct": 105,
        "takeProfitPct": 95,
        "hedgeStatus": "none",
    }
    service._trades.find = Mock(return_value=_AsyncCursor([doc]))
    service._market = SimpleNamespace(
        ensure_symbols=AsyncMock(),
        latest_tickers={
            "P-BTC-70000-270726": SimpleNamespace(
                mark_price=40, last_price=None, bid=None, ask=None
            )
        },
    )
    service._maybe_move_sl_to_breakeven = AsyncMock(side_effect=lambda _u, d, _p: d)
    service._open_live_hedge = AsyncMock()
    service._reconcile_broker_bracket = AsyncMock(return_value="protected")
    config = config_to_view(_default_config("user-1"))
    config["pairHedgeDecayPct"] = 0.0

    await service._manage_open_premiums("user-1", config)

    service._open_live_hedge.assert_not_awaited()


@pytest.mark.asyncio
async def test_manage_flattens_pair_on_combined_max_loss():
    service = _service()
    doc = {
        "_id": "trade-1",
        "optionSymbol": "P-BTC-70000-270726",
        "premiumReceived": 100,
        "livePremium": 200,
        "stopLossPct": 105,
        "takeProfitPct": 95,
        "hedgeStatus": "open",
        "hedgeSymbol": "C-BTC-70000-270726",
        "hedgePremiumReceived": 100,
        "hedgeLivePremium": 200,
        "hedgeLots": 100,
        "lots": 100,
        "contractValue": 0.001,
        "underlying": "BTC",
    }
    # main pnl = (100-200)*0.001*100 = -10; hedge same = -10; combined -20 <= -10 maxRisk
    service._trades.find = Mock(return_value=_AsyncCursor([doc]))
    service._market = SimpleNamespace(
        ensure_symbols=AsyncMock(),
        latest_tickers={
            "P-BTC-70000-270726": SimpleNamespace(
                mark_price=200, last_price=None, bid=None, ask=None
            ),
            "C-BTC-70000-270726": SimpleNamespace(
                mark_price=200, last_price=None, bid=None, ask=None
            ),
        },
    )
    service._maybe_move_sl_to_breakeven = AsyncMock(side_effect=lambda _u, d, _p: d)
    service._open_live_hedge = AsyncMock()
    service._reconcile_broker_bracket = AsyncMock(return_value="protected")
    service._close_live_trade = AsyncMock(return_value=True)
    config = config_to_view(_default_config("user-1"))
    config["pairHedgeDecayPct"] = 40.0
    config["maxRisk"] = 10.0

    await service._manage_open_premiums("user-1", config)

    service._close_live_trade.assert_awaited_once()
    assert service._close_live_trade.await_args.kwargs["reason"] == "max_loss"
    service._reconcile_broker_bracket.assert_not_awaited()


@pytest.mark.asyncio
async def test_manage_flattens_unhedged_main_on_max_loss():
    service = _service()
    doc = {
        "_id": "trade-1",
        "optionSymbol": "P-BTC-63400-170826",
        "premiumReceived": 540.80,
        "livePremium": 654.10,
        "stopLossPct": 15,
        "takeProfitPct": 60,
        "lots": 184,
        "contractValue": 0.001,
        "underlying": "BTC",
        "hedgeStatus": "none",
    }
    service._trades.find = Mock(return_value=_AsyncCursor([doc]))
    service._market = SimpleNamespace(
        ensure_symbols=AsyncMock(),
        latest_tickers={
            "P-BTC-63400-170826": SimpleNamespace(
                mark_price=654.10, last_price=None, bid=None, ask=None
            )
        },
    )
    service._indicator_snapshot = AsyncMock(return_value=None)
    service._maybe_move_sl_to_breakeven = AsyncMock(side_effect=lambda _u, d, _p: d)
    service._open_live_hedge = AsyncMock()
    service._reconcile_broker_bracket = AsyncMock(return_value="protected")
    service._close_live_trade = AsyncMock(return_value=True)
    config = config_to_view(_default_config("user-1"))
    config["pairHedgeDecayPct"] = 0.0
    config["maxRisk"] = 15.0

    await service._manage_open_premiums("user-1", config)

    service._close_live_trade.assert_awaited_once()
    assert service._close_live_trade.await_args.kwargs["reason"] == "max_loss"
    service._reconcile_broker_bracket.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_broker_exit_closes_open_hedge():
    service = _service()
    service._trades.update_one = AsyncMock(
        return_value=SimpleNamespace(modified_count=1)
    )
    service._close_hedge_if_open = AsyncMock(return_value=True)
    service._maybe_reenter_after_close = AsyncMock()
    doc = {
        "_id": "trade-1",
        "optionSymbol": "P-BTC-70000-270726",
        "direction": "LONG",
        "premiumReceived": 100,
        "lots": 1,
        "contractValue": 0.001,
        "hedgeStatus": "open",
        "hedgeSymbol": "C-BTC-70000-270726",
        "hedgePremiumReceived": 80,
    }

    await service._record_broker_bracket_exit(
        "user-1",
        doc,
        reason="take_profit",
        exit_price=5.0,
        close_order_id=99,
    )

    service._close_hedge_if_open.assert_awaited_once()
    assert service._close_hedge_if_open.await_args.kwargs["hedge_reason"] == "pair_stop"


def test_trade_to_view_exposes_pair_pnl():
    from cryptobridge.services.st_options_service import trade_to_view

    view = trade_to_view(
        {
            "_id": "abc",
            "status": "open",
            "optionSymbol": "P-BTC-70000-270726",
            "premiumReceived": 100,
            "livePremium": 60,
            "lots": 10,
            "contractValue": 0.001,
            "hedgeStatus": "open",
            "hedgeSymbol": "C-BTC-70000-270726",
            "hedgePremiumReceived": 50,
            "hedgeLivePremium": 40,
            "hedgeLots": 10,
        }
    )
    assert view["livePnl"] == pytest.approx(0.4)
    assert view["hedgeLivePnl"] == pytest.approx(0.1)
    assert view["pairLivePnl"] == pytest.approx(0.5)
    assert view["hedgeStatus"] == "open"


@pytest.mark.asyncio
async def test_patch_config_hot_toggles_hedge_immediately():
    service = _service()
    service._config = SimpleNamespace(
        find_one=AsyncMock(
            return_value={
                **_default_config("user-1"),
                "enabled": True,
                "pairHedgeDecayPct": 0.0,
            }
        ),
        update_one=AsyncMock(),
    )
    service._publish_session = AsyncMock()
    service._manage_open_premiums = AsyncMock()
    service.get_config = AsyncMock(
        side_effect=[
            {**config_to_view(_default_config("user-1")), "enabled": True, "pairHedgeDecayPct": 0.0},
            {**config_to_view(_default_config("user-1")), "enabled": True, "pairHedgeDecayPct": 25.0},
        ]
    )

    view = await service.patch_config({"id": "user-1"}, {"pairHedgeDecayPct": 25})

    assert view["pairHedgeDecayPct"] == 25.0
    service._manage_open_premiums.assert_awaited_once()
    assert service._manage_open_premiums.await_args.args[1]["pairHedgeDecayPct"] == 25.0
    assert service._publish_session.await_count >= 2


@pytest.mark.asyncio
async def test_tick_user_reloads_config_from_mongo():
    service = _service()
    fresh = {
        **config_to_view(_default_config("user-1")),
        "enabled": True,
        "pairHedgeDecayPct": 30.0,
    }
    stale = {
        **config_to_view(_default_config("user-1")),
        "enabled": True,
        "pairHedgeDecayPct": 0.0,
    }
    service.get_config = AsyncMock(return_value=fresh)
    service._last_tick_at = {}
    service._market = SimpleNamespace(ensure_symbols=AsyncMock())
    service._reconcile_pending_entries = AsyncMock()
    service._force_close_expiring = AsyncMock()
    service._manage_open_premiums = AsyncMock()
    service._process_new_bar = AsyncMock()
    service._publish_session = AsyncMock()

    await service._tick_user("user-1", stale)

    service._manage_open_premiums.assert_awaited_once_with("user-1", fresh)
    service._reconcile_pending_entries.assert_awaited_once_with("user-1", fresh)


@pytest.mark.asyncio
async def test_manage_flattens_on_frozen_hedge_stop():
    service = _service()
    doc = {
        "_id": "trade-1",
        "optionSymbol": "P-BTC-70000-270726",
        "premiumReceived": 500,
        "livePremium": 400,
        "stopLossPct": 105,
        "takeProfitPct": 95,
        "hedgeStatus": "open",
        "hedgeSymbol": "C-BTC-70000-270726",
        "hedgePremiumReceived": 400,
        "hedgeLivePremium": 680,
        "hedgeStopPremium": 675,
        "hedgeLots": 1,
        "lots": 1,
        "contractValue": 1.0,
        "underlying": "BTC",
    }
    service._trades.find = Mock(return_value=_AsyncCursor([doc]))
    service._market = SimpleNamespace(
        ensure_symbols=AsyncMock(),
        latest_tickers={
            "P-BTC-70000-270726": SimpleNamespace(
                mark_price=400, last_price=None, bid=None, ask=None
            ),
            "C-BTC-70000-270726": SimpleNamespace(
                mark_price=680, last_price=None, bid=None, ask=None
            ),
        },
    )
    service._maybe_move_sl_to_breakeven = AsyncMock(side_effect=lambda _u, d, _p: d)
    service._open_live_hedge = AsyncMock()
    service._reconcile_hedge_broker_stop = AsyncMock(return_value=False)
    service._reconcile_broker_bracket = AsyncMock(return_value="protected")
    service._close_live_trade = AsyncMock(return_value=True)
    config = config_to_view(_default_config("user-1"))
    config["pairHedgeDecayPct"] = 40.0
    config["maxRisk"] = 75.0

    await service._manage_open_premiums("user-1", config)

    service._close_live_trade.assert_awaited_once()
    assert service._close_live_trade.await_args.kwargs["reason"] == "max_loss"


def test_limit_entry_filled_without_average_fill_price():
    from cryptobridge.services.st_options_service import (
        _is_limit_entry_filled,
        _order_filled_size,
    )

    closed = SimpleNamespace(
        status="CLOSED",
        size=2.0,
        unfilled_size=0.0,
        average_fill_price=None,
    )
    assert _is_limit_entry_filled(closed) is True
    assert _order_filled_size(closed) == 2.0

    partial = SimpleNamespace(
        status="CANCELLED",
        size=3.0,
        unfilled_size=1.0,
        average_fill_price=410.0,
    )
    assert _is_limit_entry_filled(partial) is True
    assert _order_filled_size(partial) == 2.0

    cancelled = SimpleNamespace(
        status="CANCELLED",
        size=1.0,
        unfilled_size=1.0,
        average_fill_price=None,
    )
    assert _is_limit_entry_filled(cancelled) is False
    assert _order_filled_size(cancelled) == 0.0

    cancelled_but_avg = SimpleNamespace(
        status="CANCELLED",
        size=2.0,
        unfilled_size=2.0,
        average_fill_price=411.0,
    )
    assert _is_limit_entry_filled(cancelled_but_avg) is True
    assert _order_filled_size(cancelled_but_avg) == 2.0


@pytest.mark.asyncio
async def test_await_limit_fill_recovers_fill_after_cancel_race():
    service = _service()
    placed = SimpleNamespace(
        id=99,
        status="PENDING",
        size=1.0,
        unfilled_size=1.0,
        average_fill_price=None,
    )
    still_open = SimpleNamespace(
        id=99,
        status="PENDING",
        size=1.0,
        unfilled_size=1.0,
        average_fill_price=None,
    )
    filled_after_cancel = SimpleNamespace(
        id=99,
        status="CLOSED",
        size=1.0,
        unfilled_size=0.0,
        average_fill_price=412.5,
    )
    # Poll window: never filled; force-cancel first sees open, then filled (race).
    service._delta.fetch_order = AsyncMock(
        side_effect=[still_open] * 9 + [filled_after_cancel]
    )
    service._delta.cancel_order = AsyncMock()

    result = await service._await_limit_fill_or_cancel(
        "key", "secret", placed, poll_attempts=8
    )

    assert result is filled_after_cancel
    service._delta.cancel_order.assert_awaited_once_with("key", "secret", 99)


@pytest.mark.asyncio
async def test_await_limit_fill_returns_none_when_truly_cancelled():
    service = _service()
    placed = SimpleNamespace(
        id=42,
        status="PENDING",
        size=1.0,
        unfilled_size=1.0,
        average_fill_price=None,
    )
    open_poll = SimpleNamespace(
        id=42,
        status="PENDING",
        size=1.0,
        unfilled_size=1.0,
        average_fill_price=None,
    )
    cancelled = SimpleNamespace(
        id=42,
        status="CANCELLED",
        size=1.0,
        unfilled_size=1.0,
        average_fill_price=None,
        product_id=1,
        order_type="limit_order",
        side="SELL",
        limit_price=400.0,
        created_at="",
    )
    service._delta.fetch_order = AsyncMock(side_effect=[open_poll] * 3 + [cancelled] * 5)
    service._delta.cancel_order = AsyncMock()
    service._delta.fetch_margined_positions = AsyncMock(return_value=[])
    service._delta.fetch_fills = AsyncMock(return_value=[])

    result = await service._await_limit_fill_or_cancel(
        "key",
        "secret",
        placed,
        product_symbol="P-BTC-70000-270726",
        fallback_limit=400.0,
        poll_attempts=3,
    )

    assert result is None
    # Already cancelled on the first force-cancel fetch — no extra cancel required.
    assert service._delta.cancel_order.await_count == 0


@pytest.mark.asyncio
async def test_await_limit_fill_recovers_after_cancel_404_then_position():
    service = _service()
    placed = SimpleNamespace(
        id=55,
        status="PENDING",
        size=2.0,
        unfilled_size=2.0,
        average_fill_price=None,
        product_id=9,
        order_type="limit_order",
        side="SELL",
        limit_price=554.0,
        created_at="",
    )
    cancelled = SimpleNamespace(
        id=55,
        status="CANCELLED",
        size=2.0,
        unfilled_size=2.0,
        average_fill_price=None,
        product_id=9,
        order_type="limit_order",
        side="SELL",
        limit_price=554.0,
        created_at="",
    )
    service._delta.fetch_order = AsyncMock(return_value=cancelled)
    service._delta.cancel_order = AsyncMock(
        side_effect=RuntimeError("Delta API request failed: HTTP 404 Not Found")
    )
    service._delta.fetch_fills = AsyncMock(return_value=[])
    empty = []
    short = [
        {
            "product_symbol": "C-BTC-63800-120826",
            "size": -240,
            "entry_price": "555.0",
        }
    ]
    # First few position polls empty (lag), then short appears.
    service._delta.fetch_margined_positions = AsyncMock(side_effect=[empty, empty, short])

    result = await service._await_limit_fill_or_cancel(
        "key",
        "secret",
        placed,
        product_symbol="C-BTC-63800-120826",
        fallback_limit=554.0,
        poll_attempts=1,
    )

    assert result is not None
    assert result.status == "CLOSED"
    assert float(result.size) == 240.0
    assert float(result.average_fill_price) == 555.0


@pytest.mark.asyncio
async def test_await_limit_fill_recovers_short_position_after_cancel():
    service = _service()
    placed = SimpleNamespace(
        id=77,
        status="PENDING",
        size=2.0,
        unfilled_size=2.0,
        average_fill_price=None,
        product_id=9,
        order_type="limit_order",
        side="SELL",
        limit_price=410.0,
        created_at="",
    )
    cancelled = SimpleNamespace(
        id=77,
        status="CANCELLED",
        size=2.0,
        unfilled_size=2.0,
        average_fill_price=None,
        product_id=9,
        order_type="limit_order",
        side="SELL",
        limit_price=410.0,
        created_at="",
    )
    service._delta.fetch_order = AsyncMock(return_value=cancelled)
    service._delta.cancel_order = AsyncMock()
    service._delta.fetch_fills = AsyncMock(return_value=[])
    service._delta.fetch_margined_positions = AsyncMock(
        return_value=[
            {
                "product_symbol": "P-BTC-70000-270726",
                "size": -2,
                "entry_price": "412.5",
            }
        ]
    )

    result = await service._await_limit_fill_or_cancel(
        "key",
        "secret",
        placed,
        product_symbol="P-BTC-70000-270726",
        fallback_limit=410.0,
        poll_attempts=1,
    )

    assert result is not None
    assert result.status == "CLOSED"
    assert float(result.size) == 2.0
    assert float(result.average_fill_price) == 412.5
    assert float(result.unfilled_size) == 0.0


@pytest.mark.asyncio
async def test_reconcile_pending_keeps_row_until_confirm_threshold():
    from datetime import datetime, timezone

    service = _service()
    created = datetime.now(timezone.utc)
    doc = {
        "_id": "pending-keep",
        "userId": "user-1",
        "optionSymbol": "C-BTC-63800-120826",
        "entryOrderId": 1464507831,
        "entryLimitPrice": 554.0,
        "premiumReceived": 554.0,
        "lots": 240,
        "createdAt": created,
        "unfilledConfirmCount": 0,
        "status": STATUS_PENDING_ENTRY,
    }

    async def _find():
        yield doc

    service._trades.find = Mock(return_value=_find())
    service._trades.update_one = AsyncMock()
    service._trades.delete_one = AsyncMock()
    service._trade_credentials = AsyncMock(return_value=("key", "secret"))
    service._delta.fetch_order = AsyncMock(
        return_value=SimpleNamespace(
            status="CANCELLED",
            size=240.0,
            unfilled_size=240.0,
            average_fill_price=None,
        )
    )
    service._delta.fetch_margined_positions = AsyncMock(return_value=[])
    service._delta.fetch_fills = AsyncMock(return_value=[])
    service._promote_pending_entry = AsyncMock()

    await service._reconcile_pending_entries("user-1", {"underlying": "BTC"})

    service._trades.delete_one.assert_not_awaited()
    service._promote_pending_entry.assert_not_awaited()
    service._trades.update_one.assert_awaited()
    assert service._trades.update_one.await_args.args[1]["$set"]["unfilledConfirmCount"] == 1


@pytest.mark.asyncio
async def test_await_limit_fill_retries_cancel_when_404_still_pending(monkeypatch):
    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(
        "cryptobridge.services.st_options_service.asyncio.sleep",
        _noop,
    )
    service = _service()
    pending = SimpleNamespace(
        id=88,
        status="PENDING",
        size=184.0,
        unfilled_size=184.0,
        average_fill_price=None,
        product_id=9,
        order_type="limit_order",
        side="SELL",
        limit_price=539.8,
        created_at="",
    )
    service._delta.fetch_order = AsyncMock(return_value=pending)
    service._delta.cancel_order = AsyncMock(
        side_effect=RuntimeError("Delta API request failed: HTTP 404 Not Found")
    )
    service._delta.cancel_all_entry_orders = AsyncMock()
    service._delta.fetch_product = AsyncMock(return_value=_product())
    service._delta.fetch_fills = AsyncMock(return_value=[])
    service._delta.fetch_margined_positions = AsyncMock(return_value=[])

    result = await service._await_limit_fill_or_cancel(
        "key",
        "secret",
        pending,
        product=_product(),
        product_symbol="P-BTC-63400-170826",
        fallback_limit=539.8,
        poll_attempts=1,
    )

    assert result is None
    assert service._delta.cancel_order.await_count == ENTRY_CANCEL_RETRIES
    service._delta.cancel_all_entry_orders.assert_awaited()


@pytest.mark.asyncio
async def test_reconcile_pending_cancels_working_limit_instead_of_waiting(monkeypatch):
    from datetime import datetime, timezone

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(
        "cryptobridge.services.st_options_service.asyncio.sleep",
        _noop,
    )
    service = _service()
    doc = {
        "_id": "pending-open",
        "userId": "user-1",
        "optionSymbol": "P-BTC-63400-170826",
        "entryOrderId": 99,
        "entryLimitPrice": 539.8,
        "premiumReceived": 539.8,
        "lots": 132,
        "createdAt": datetime.now(timezone.utc),
        "unfilledConfirmCount": 0,
        "status": STATUS_PENDING_ENTRY,
    }

    async def _find():
        yield doc

    pending = SimpleNamespace(
        id=99,
        status="PENDING",
        size=132.0,
        unfilled_size=132.0,
        average_fill_price=None,
    )
    service._trades.find = Mock(return_value=_find())
    service._trades.update_one = AsyncMock()
    service._trades.delete_one = AsyncMock()
    service._trade_credentials = AsyncMock(return_value=("key", "secret"))
    service._delta.fetch_order = AsyncMock(return_value=pending)
    service._delta.cancel_order = AsyncMock(
        side_effect=RuntimeError("Delta API request failed: HTTP 404 Not Found")
    )
    service._delta.cancel_all_entry_orders = AsyncMock()
    service._delta.fetch_product = AsyncMock(return_value=_product())
    service._delta.fetch_margined_positions = AsyncMock(return_value=[])
    service._delta.fetch_fills = AsyncMock(return_value=[])
    service._promote_pending_entry = AsyncMock()

    await service._reconcile_pending_entries("user-1", {"underlying": "BTC"})

    assert service._delta.cancel_order.await_count >= ENTRY_CANCEL_RETRIES
    service._trades.delete_one.assert_not_awaited()
    service._promote_pending_entry.assert_not_awaited()
    assert service._trades.update_one.await_args.args[1]["$set"]["unfilledConfirmCount"] == 1


@pytest.mark.asyncio
async def test_reconcile_pending_clears_working_limit_without_min_age(monkeypatch):
    from datetime import datetime, timezone

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(
        "cryptobridge.services.st_options_service.asyncio.sleep",
        _noop,
    )
    service = _service()
    doc = {
        "_id": "pending-clear",
        "userId": "user-1",
        "optionSymbol": "P-BTC-63400-170826",
        "entryOrderId": 99,
        "entryLimitPrice": 539.8,
        "premiumReceived": 539.8,
        "lots": 132,
        "createdAt": datetime.now(timezone.utc),
        "unfilledConfirmCount": 2,
        "status": STATUS_PENDING_ENTRY,
    }

    async def _find():
        yield doc

    pending = SimpleNamespace(
        id=99,
        status="PENDING",
        size=132.0,
        unfilled_size=132.0,
        average_fill_price=None,
    )
    service._trades.find = Mock(return_value=_find())
    service._trades.update_one = AsyncMock()
    service._trades.delete_one = AsyncMock()
    service._trade_credentials = AsyncMock(return_value=("key", "secret"))
    service._delta.fetch_order = AsyncMock(return_value=pending)
    service._delta.cancel_order = AsyncMock(
        side_effect=RuntimeError("Delta API request failed: HTTP 404 Not Found")
    )
    service._delta.cancel_all_entry_orders = AsyncMock()
    service._delta.fetch_product = AsyncMock(return_value=_product())
    service._delta.fetch_margined_positions = AsyncMock(return_value=[])
    service._delta.fetch_fills = AsyncMock(return_value=[])
    service._promote_pending_entry = AsyncMock()

    await service._reconcile_pending_entries("user-1", {"underlying": "BTC"})

    service._promote_pending_entry.assert_not_awaited()
    service._trades.delete_one.assert_awaited()
    user_message = service._push_activity.call_args.kwargs["user_message"]
    assert "Setup skipped — limit entry did not fill" in user_message


@pytest.mark.asyncio
async def test_sync_broker_shorts_adopts_orphan_and_attaches_bracket():
    service = _service()
    service._load_user = AsyncMock(return_value={"id": "user-1", "selectedAccountId": "acc-1"})
    service._selected_account = AsyncMock(return_value={"_id": "acc-1"})
    service._credentials = Mock(return_value=("key", "secret"))
    service._list_trade_docs = AsyncMock(return_value=[])
    service._trades.find = Mock(return_value=_async_empty())
    service._trades.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id="adopted-1"))
    service._attach_bracket_protection = AsyncMock(return_value=True)
    service._delta.fetch_margined_positions = AsyncMock(
        return_value=[
            {
                "product_symbol": "C-BTC-63800-120826",
                "size": -240,
                "entry_price": "555.0",
            }
        ]
    )
    service._delta.fetch_product = AsyncMock(return_value=_product())
    product = _product()
    product.symbol = "C-BTC-63800-120826"
    service._delta.fetch_product = AsyncMock(return_value=product)

    await service._sync_broker_shorts_with_st(
        "user-1",
        {
            "underlying": "BTC",
            "stopLossPct": 15.0,
            "takeProfitPct": 60.0,
            "breakevenDecayPct": 40.0,
        },
    )

    service._trades.insert_one.assert_awaited_once()
    inserted = service._trades.insert_one.await_args.args[0]
    assert inserted["optionSymbol"] == "C-BTC-63800-120826"
    assert inserted["status"] == "open"
    assert inserted["direction"] == "SHORT"
    assert inserted["adoptedFromBroker"] is True
    assert inserted["lots"] == 240
    service._attach_bracket_protection.assert_awaited_once()


def _async_empty():
    async def _gen():
        if False:
            yield None

    return _gen()


@pytest.mark.asyncio
async def test_sync_retries_missing_brackets_on_open_trade():
    service = _service()
    service._load_user = AsyncMock(return_value={"id": "user-1"})
    service._selected_account = AsyncMock(return_value={"_id": "acc-1"})
    service._credentials = Mock(return_value=("key", "secret"))
    open_doc = {
        "_id": "open-1",
        "optionSymbol": "C-BTC-63800-120826",
        "status": STATUS_OPEN,
        "bracketAttached": False,
        "stopOrderId": None,
        "takeProfitOrderId": None,
        "stopPremium": 600.0,
        "targetPremium": 200.0,
    }
    service._list_trade_docs = AsyncMock(return_value=[open_doc])
    service._trades.find = Mock(return_value=_async_empty())
    service._trade_credentials = AsyncMock(return_value=("key", "secret"))
    service._delta.fetch_margined_positions = AsyncMock(return_value=[])
    product = _product()
    product.symbol = "C-BTC-63800-120826"
    service._delta.fetch_product = AsyncMock(return_value=product)
    service._attach_bracket_protection = AsyncMock(return_value=True)
    service._trades.insert_one = AsyncMock()

    await service._sync_broker_shorts_with_st("user-1", {"underlying": "BTC"})

    service._attach_bracket_protection.assert_awaited_once()
    service._trades.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_promote_pending_entry_attaches_bracket():
    service = _service()
    doc = {
        "_id": "pending-1",
        "optionSymbol": "P-BTC-70000-270726",
        "stopLossPct": 105.0,
        "takeProfitPct": 95.0,
        "entryOrderId": 77,
        "bracketAttached": False,
    }
    service._trades.update_one = AsyncMock()
    service._attach_bracket_protection = AsyncMock(return_value=True)
    product = _product()
    product.symbol = "P-BTC-70000-270726"

    out = await service._promote_pending_entry(
        "user-1",
        doc,
        fill=412.5,
        lots=2,
        product=product,
        api_key="key",
        api_secret="secret",
        recovered_from_position=True,
    )

    assert out["status"] == "open"
    assert out["premiumReceived"] == 412.5
    assert out["lots"] == 2
    service._attach_bracket_protection.assert_awaited_once()
    assert service._push_activity.call_args.kwargs["level"] == "warn"


def test_order_failure_user_message_insufficient_margin():
    from fastapi.exceptions import HTTPException

    from cryptobridge.services.st_options_service import _order_failure_user_message

    exc = HTTPException(
        status_code=502,
        detail={
            "error": (
                'Delta API request failed: {"error":{"code":"insufficient_margin",'
                '"context":{"available_balance":"100.5","required_additional_balance":"50.25"}},'
                '"success":false}'
            )
        },
    )
    msg = _order_failure_user_message(exc, kind="setup")
    assert "insufficient margin" in msg
    assert "50.25" in msg
    assert "100.50" in msg or "100.5" in msg


@pytest.mark.asyncio
async def test_maybe_close_if_broker_flat_records_fill_price():
    service = _service()
    doc = {
        "_id": "trade-flat",
        "userId": "user-1",
        "accountId": "account-1",
        "direction": "LONG",
        "status": STATUS_OPEN,
        "underlying": "BTC",
        "optionSymbol": "P-BTC-65000-100826",
        "premiumReceived": 500,
        "livePremium": 480,
        "contractValue": 0.001,
        "lots": 10,
        "entryTime": 1_700_000_000,
        "hedgeStatus": "none",
    }
    service._trade_credentials = AsyncMock(return_value=("key", "secret"))
    service._find_short_option_position = AsyncMock(return_value=None)
    service._lookup_cover_fill_price = AsyncMock(return_value=420.0)
    service._record_broker_bracket_exit = AsyncMock()

    closed = await service._maybe_close_if_broker_flat("user-1", doc)

    assert closed is True
    service._record_broker_bracket_exit.assert_awaited_once()
    kwargs = service._record_broker_bracket_exit.await_args.kwargs
    assert kwargs["reason"] == "broker_flat"
    assert kwargs["exit_price"] == 420.0
    assert kwargs["hedge_broker_reduce"] is False


@pytest.mark.asyncio
async def test_maybe_close_if_broker_flat_skips_when_short_remains():
    service = _service()
    doc = {
        "_id": "trade-open",
        "status": STATUS_OPEN,
        "optionSymbol": "P-BTC-65000-100826",
    }
    service._trade_credentials = AsyncMock(return_value=("key", "secret"))
    service._find_short_option_position = AsyncMock(return_value=(2.0, 500.0))
    service._record_broker_bracket_exit = AsyncMock()

    closed = await service._maybe_close_if_broker_flat("user-1", doc)

    assert closed is False
    service._record_broker_bracket_exit.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_fill_from_bracket_uses_fills_when_avg_missing():
    service = _service()
    doc = {
        "_id": "trade-1",
        "optionSymbol": "P-BTC-65000-100826",
        "premiumReceived": 500,
        "stopPremium": 1025,
        "targetPremium": 25,
        "livePremium": 400,
        "entryTime": 1_700_000_000,
        "lots": 1,
        "contractValue": 0.001,
        "underlying": "BTC",
        "status": STATUS_OPEN,
    }
    service._lookup_cover_fill_price = AsyncMock(return_value=390.0)
    service._record_broker_bracket_exit = AsyncMock()
    service._delta.fetch_order = AsyncMock(return_value=None)
    service._delta.cancel_order = AsyncMock()
    triggered = SimpleNamespace(id=99, average_fill_price=None, status="CLOSED")

    await service._record_fill_from_bracket(
        "user-1",
        doc,
        reason="take_profit",
        triggered_order=triggered,
        sibling_id=None,
        api_key="key",
        api_secret="secret",
    )

    assert service._record_broker_bracket_exit.await_args.kwargs["exit_price"] == 390.0
