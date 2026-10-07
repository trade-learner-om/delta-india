import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from cryptobridge.delta.request_signing import (
    DELTA_SIGN_EXTENSION,
    DeltaSignContext,
    apply_delta_signature,
    build_signature_payload,
    clock_offset_from_expired_signature,
    is_expired_signature_response,
    make_delta_sign_hook,
    signed_path_from_request,
)
from cryptobridge.delta.rest_client import DeltaRestClient
from cryptobridge.utils.signing import sign_delta


def test_build_signature_payload_includes_body_for_post():
    assert build_signature_payload("POST", "123", "/v2/orders", '{"a":1}') == 'POST123/v2/orders{"a":1}'


def test_apply_delta_signature_stamps_headers_at_send_time():
    request = httpx.Request("GET", "https://api.india.delta.exchange/v2/positions/margined")
    with patch("cryptobridge.delta.request_signing.time.time", return_value=1_700_000_000.0):
        apply_delta_signature(request, api_key="key", api_secret="secret", clock_offset=2.0)
    assert request.headers["api-key"] == "key"
    assert request.headers["timestamp"] == "1700000002"
    expected = sign_delta("secret", "GET1700000002/v2/positions/margined")
    assert request.headers["signature"] == expected


def test_sign_hook_uses_request_extension():
    request = httpx.Request("GET", "https://api.india.delta.exchange/v2/orders")
    request.extensions[DELTA_SIGN_EXTENSION] = DeltaSignContext(api_key="k", api_secret="s")
    hook = make_delta_sign_hook(lambda: 0.0)

    async def _run():
        with patch("cryptobridge.delta.request_signing.time.time", return_value=99.0):
            await hook(request)

    import asyncio

    asyncio.run(_run())
    assert request.headers["timestamp"] == "99"
    assert request.headers["signature"] == sign_delta("s", "GET99/v2/orders")


def test_signed_path_includes_query_string():
    request = httpx.Request(
        "GET",
        "https://api.india.delta.exchange/v2/orders/history?limit=10&page=2",
    )
    assert signed_path_from_request(request) == "/v2/orders/history?limit=10&page=2"


def test_is_expired_signature_response():
    body = json.dumps(
        {
            "success": False,
            "error": {
                "code": "expired_signature",
                "context": {"request_time": 100, "server_time": 140},
            },
        }
    )
    response = httpx.Response(401, text=body, request=httpx.Request("GET", "https://example.com"))
    assert is_expired_signature_response(response)
    assert clock_offset_from_expired_signature(response) == 40.0


@pytest.mark.asyncio
async def test_signed_get_retries_once_on_expired_signature():
    client = DeltaRestClient()
    await client.start()

    expired_body = json.dumps(
        {
            "success": False,
            "error": {
                "code": "expired_signature",
                "context": {"request_time": 100, "server_time": 140},
            },
        }
    )
    ok_body = json.dumps({"success": True, "result": []})

    expired = httpx.Response(401, text=expired_body, request=httpx.Request("GET", "https://example.com"))
    ok = httpx.Response(200, text=ok_body, request=httpx.Request("GET", "https://example.com"))

    mock_get = AsyncMock(side_effect=[expired, ok])
    http_client = client._client_or_raise()
    with patch.object(http_client, "get", mock_get):
        node = await client._signed_get("/v2/positions/margined", "key", "secret")

    assert node["success"] is True
    assert mock_get.await_count == 2
    assert client.clock_offset() == 40.0

    await client.stop()


@pytest.mark.asyncio
async def test_should_skip_rest_refresh_when_ws_subscribed_and_recent():
    from cryptobridge.delta.private_stream import REST_REFRESH_MIN_INTERVAL_SEC, _AccountStream

    stream = _AccountStream(account_id="acc1", api_key="k", api_secret="s")
    stream.status = "subscribed"
    stream.last_rest_refresh_at = __import__("time").monotonic()

    assert stream.should_skip_rest_refresh(force=False) is True
    assert stream.should_skip_rest_refresh(force=True) is False

    stream.last_rest_refresh_at = __import__("time").monotonic() - REST_REFRESH_MIN_INTERVAL_SEC - 1
    assert stream.should_skip_rest_refresh(force=False) is False

    stream.status = "connecting"
    assert stream.should_skip_rest_refresh(force=False) is False
