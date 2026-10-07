import pytest

from cryptobridge.delta.private_stream import _AccountStream, DeltaPrivateStreamService


class FakeAccounts:
    pass


class FakeDelta:
    pass


@pytest.mark.asyncio
async def test_handle_positions_message_merges_partial_updates():
    service = DeltaPrivateStreamService(FakeAccounts(), FakeDelta())  # type: ignore[arg-type]
    stream = _AccountStream(account_id="acc1", api_key="key", api_secret="secret")
    stream.positions["C-BTC-59500-030726"] = {
        "product_symbol": "C-BTC-59500-030726",
        "size": -80,
        "entry_price": 1240.0,
        "mark_price": 540.2,
        "unrealized_pnl": 44.08,
    }

    await service._handle_positions_message(
        stream,
        {
            "type": "positions",
            "positions": [
                {
                    "product_symbol": "C-BTC-59500-030726",
                    "size": -80,
                    "unrealized_pnl": 51.25,
                }
            ],
        },
    )

    updated = stream.positions["C-BTC-59500-030726"]
    assert updated["entry_price"] == 1240.0
    assert updated["mark_price"] == 540.2
    assert updated["unrealized_pnl"] == 51.25


@pytest.mark.asyncio
async def test_handle_positions_snapshot_replaces_cache():
    service = DeltaPrivateStreamService(FakeAccounts(), FakeDelta())  # type: ignore[arg-type]
    stream = _AccountStream(account_id="acc1", api_key="key", api_secret="secret")
    stream.positions["C-BTC-59500-030726"] = {
        "product_symbol": "C-BTC-59500-030726",
        "size": -80,
    }

    await service._handle_positions_message(
        stream,
        {
            "type": "positions",
            "action": "snapshot",
            "result": [
                {
                    "product_symbol": "C-BTC-60000-030726",
                    "size": 40,
                    "entry_price": 900.0,
                }
            ],
        },
    )

    assert "C-BTC-59500-030726" not in stream.positions
    assert stream.positions["C-BTC-60000-030726"]["size"] == 40


@pytest.mark.asyncio
async def test_handle_positions_delete_removes_symbol():
    service = DeltaPrivateStreamService(FakeAccounts(), FakeDelta())  # type: ignore[arg-type]
    stream = _AccountStream(account_id="acc1", api_key="key", api_secret="secret")
    stream.positions["C-BTC-59500-030726"] = {
        "product_symbol": "C-BTC-59500-030726",
        "size": -80,
    }

    await service._handle_positions_message(
        stream,
        {
            "type": "positions",
            "action": "delete",
            "symbol": "C-BTC-59500-030726",
        },
    )

    assert "C-BTC-59500-030726" not in stream.positions


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [0, "0", 0.0])
async def test_handle_positions_zero_size_removes_symbol(size):
    service = DeltaPrivateStreamService(FakeAccounts(), FakeDelta())  # type: ignore[arg-type]
    stream = _AccountStream(account_id="acc1", api_key="key", api_secret="secret")
    stream.positions["C-BTC-59500-030726"] = {
        "product_symbol": "C-BTC-59500-030726",
        "size": -80,
    }

    await service._handle_positions_message(
        stream,
        {
            "type": "positions",
            "action": "update",
            "symbol": "C-BTC-59500-030726",
            "size": size,
        },
    )

    assert "C-BTC-59500-030726" not in stream.positions


@pytest.mark.asyncio
async def test_positions_listener_notified_on_delete():
    service = DeltaPrivateStreamService(FakeAccounts(), FakeDelta())  # type: ignore[arg-type]
    stream = _AccountStream(account_id="acc1", api_key="key", api_secret="secret")
    stream.positions["C-BTC-59500-030726"] = {"product_symbol": "C-BTC-59500-030726", "size": -80}
    notified: list[str] = []

    service.add_positions_listener(lambda account_id: notified.append(account_id))

    await service._handle_positions_message(
        stream,
        {
            "type": "positions",
            "action": "delete",
            "symbol": "C-BTC-59500-030726",
        },
    )

    assert notified == ["acc1"]


@pytest.mark.asyncio
async def test_handle_orders_snapshot_replaces_cache():
    service = DeltaPrivateStreamService(FakeAccounts(), FakeDelta())  # type: ignore[arg-type]
    stream = _AccountStream(account_id="acc1", api_key="key", api_secret="secret")
    stream.orders["99"] = {"id": 99, "status": "open"}

    await service._handle_orders_message(
        stream,
        {
            "type": "orders",
            "action": "snapshot",
            "result": [
                {"id": 101, "state": "open", "symbol": "BTCUSD"},
            ],
        },
    )

    assert "99" not in stream.orders
    assert stream.orders["101"]["symbol"] == "BTCUSD"


@pytest.mark.asyncio
async def test_handle_orders_delete_removes_order():
    service = DeltaPrivateStreamService(FakeAccounts(), FakeDelta())  # type: ignore[arg-type]
    stream = _AccountStream(account_id="acc1", api_key="key", api_secret="secret")
    stream.orders["55"] = {"id": 55, "state": "open"}

    await service._handle_orders_message(
        stream,
        {
            "type": "orders",
            "action": "delete",
            "order_id": 55,
        },
    )

    assert "55" not in stream.orders
