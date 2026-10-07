import pytest
from fastapi import HTTPException

from cryptobridge.delta.rest_client import DeltaRestClient, normalize_order_size


def test_normalize_order_size_whole_contracts():
    assert normalize_order_size(120.0) == 120
    assert normalize_order_size(120) == 120
    assert normalize_order_size(1.5) == 1
    assert isinstance(normalize_order_size(33.0), int)


def test_normalize_order_size_rejects_zero():
    with pytest.raises(ValueError):
        normalize_order_size(0.9)


def test_map_instrument_rejects_null_node():
    client = DeltaRestClient()
    with pytest.raises(HTTPException) as exc:
        client._map_instrument(None)
    assert exc.value.status_code == 404


def test_map_product_rejects_null_node():
    client = DeltaRestClient()
    with pytest.raises(HTTPException) as exc:
        client._map_product(None)
    assert exc.value.status_code == 404


def _lab_product_node():
    return {
        "symbol": "LABUSD",
        "id": 123,
        "contract_value": "10",
        "contract_unit_currency": "LAB",
        "quoting_asset": {"symbol": "USD"},
        "settling_asset": {"symbol": "USD"},
        "initial_margin": "5",
        "default_leverage": "20.000000000000000000",
        "contract_type": "perpetual_futures",
    }


def test_map_product_captures_default_leverage():
    client = DeltaRestClient()
    product = client._map_product(_lab_product_node())
    assert product.default_leverage == 20.0
    assert product.initial_margin == 5.0


def test_max_leverage_prefers_default_leverage():
    client = DeltaRestClient()
    product = client._map_product(_lab_product_node())
    assert DeltaRestClient.max_leverage_for_product(product) == 20


def test_max_leverage_uses_initial_margin_percentage_fallback():
    client = DeltaRestClient()
    node = _lab_product_node()
    node.pop("default_leverage")
    product = client._map_product(node)
    assert product.default_leverage is None
    # initial_margin is a percentage (5 -> 5% -> 20x), not a fraction.
    assert DeltaRestClient.max_leverage_for_product(product) == 20


def test_max_leverage_defaults_to_one_without_data():
    client = DeltaRestClient()
    node = _lab_product_node()
    node.pop("default_leverage")
    node.pop("initial_margin")
    product = client._map_product(node)
    assert DeltaRestClient.max_leverage_for_product(product) == 1


@pytest.mark.asyncio
async def test_fetch_products_filtered_uses_expiry_not_expiry_date():
    client = DeltaRestClient()
    captured = {}

    async def fake_public_get(path, params):
        captured["path"] = path
        captured["params"] = dict(params)
        return {"result": [], "meta": {}}

    client._public_get = fake_public_get  # type: ignore[method-assign]
    await client.fetch_products_filtered(
        underlying="BTC",
        expiry_date="2026-07-24",
        contract_types="call_options,put_options",
        max_pages=1,
    )
    assert captured["path"] == "/v2/products"
    assert captured["params"].get("expiry") == "2026-07-24"
    assert "expiry_date" not in captured["params"]
