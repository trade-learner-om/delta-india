from __future__ import annotations
import json
import logging
import math
from dataclasses import dataclass
from typing import Any

import httpx

from cryptobridge.config import settings
from cryptobridge.delta.request_signing import (
    DELTA_SIGN_EXTENSION,
    DeltaSignContext,
    clock_offset_from_expired_signature,
    expired_signature_context,
    is_expired_signature_response,
    make_delta_sign_hook,
)
from cryptobridge.delta.wallet_margin import WalletSummary, map_wallet_payload
from cryptobridge.exceptions import http_error

log = logging.getLogger(__name__)


def normalize_symbol(symbol: str | None) -> str:
    return (symbol or "").strip().upper()


def normalize_order_size(size: float) -> int:
    """Delta /v2/orders requires size as a whole-contract integer."""
    value = int(math.floor(float(size)))
    if value < 1:
        raise ValueError("Order size must be at least 1 contract.")
    return value


def _parse_number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_number_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _delta_error_message(node: dict, fallback: str) -> str:
    error = node.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or fallback)
    if isinstance(error, str) and error.strip():
        return error.strip()
    return fallback


@dataclass
class DeltaProfile:
    id: str
    account_name: str
    email: str
    sub_account: bool


@dataclass
class InstrumentSummary:
    symbol: str
    description: str
    product_id: int | None
    close_price: float | None
    mark_price: float | None
    best_bid: float | None
    best_ask: float | None
    change_24h: float | None
    tick_size: float | None = None


@dataclass
class ProductSummary:
    symbol: str
    product_id: int
    contract_value: float
    tick_size: float | None
    contract_unit_currency: str
    quoting_asset: str
    settling_asset: str = "USD"
    notional_type: str = "vanilla"
    initial_margin: float | None = None
    default_leverage: float | None = None
    taker_commission_rate: float | None = None
    maker_commission_rate: float | None = None
    contract_type: str | None = None
    strike_price: float | None = None
    expiry: str | None = None
    underlying_asset: str | None = None
    lot_size: float | None = None


@dataclass
class OrderSummary:
    id: int
    symbol: str
    product_id: int
    order_type: str
    side: str
    limit_price: float | None
    stop_price: float | None
    take_profit_price: float | None
    stop_loss_price: float | None
    size: float | None
    unfilled_size: float | None
    status: str
    created_at: str
    client_order_id: str | None = None
    stop_order_type: str | None = None
    reduce_only: bool = False
    average_fill_price: float | None = None


@dataclass
class BracketLegs:
    stop_loss_order_id: int | None = None
    take_profit_order_id: int | None = None


DEFAULT_BRACKET_STOP_TRIGGER = "mark_price"


@dataclass
class CandleBar:
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class DeltaRestClient:
    def __init__(self) -> None:
        self._base = settings.delta_api_base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None
        self._clock_offset: float = 0.0

    def clock_offset(self) -> float:
        return self._clock_offset

    def set_clock_offset(self, offset: float) -> None:
        self._clock_offset = float(offset)

    async def start(self) -> None:
        sign_hook = make_delta_sign_hook(lambda: self._clock_offset)
        self._client = httpx.AsyncClient(
            base_url=self._base,
            timeout=30.0,
            headers={"User-Agent": settings.user_agent, "Accept": "application/json"},
            event_hooks={"request": [sign_hook]},
        )
        await self._probe_clock_offset()

    async def _probe_clock_offset(self) -> None:
        """Best-effort public probe; signed offset is learned from expired_signature retries."""
        try:
            client = self._client_or_raise()
            response = await client.get("/v2/products", params={"page_size": 1})
            if response.status_code >= 400:
                return
            log.debug("Delta REST client started (clock offset=%.1fs)", self._clock_offset)
        except Exception as exc:  # noqa: BLE001
            log.debug("Delta clock probe skipped: %s", exc)

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _client_or_raise(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Delta REST client not started")
        return self._client

    async def _handle_error(self, response: httpx.Response) -> None:
        detail = response.text or response.reason_phrase
        if is_expired_signature_response(response):
            request_time, server_time = expired_signature_context(response)
            log.warning(
                "Delta expired_signature: request_time=%s server_time=%s skew=%ss",
                request_time,
                server_time,
                (server_time - request_time) if request_time is not None and server_time is not None else "?",
            )
            offset = clock_offset_from_expired_signature(response)
            if offset is not None and abs(offset) > 2:
                self._clock_offset = offset
                log.warning(
                    "Delta clock offset adjusted to %.1fs — verify host NTP sync (Windows Time on EC2)",
                    self._clock_offset,
                )
        raise http_error(502, f"Delta API request failed: {detail}")

    async def _send_signed(
        self,
        method: str,
        path: str,
        api_key: str,
        api_secret: str,
        *,
        params: dict | None = None,
        content: str | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        from urllib.parse import urlencode

        client = self._client_or_raise()
        signed_path = path
        if params:
            query = urlencode({k: str(v) for k, v in params.items() if v is not None})
            if query:
                signed_path = f"{path}?{query}"

        request_headers = dict(headers or {})
        if content is not None and "Content-Type" not in request_headers:
            request_headers["Content-Type"] = "application/json"

        extensions = {DELTA_SIGN_EXTENSION: DeltaSignContext(api_key=api_key, api_secret=api_secret)}

        async def _execute() -> httpx.Response:
            if method.upper() == "GET":
                return await client.get(signed_path, headers=request_headers, extensions=extensions)
            if method.upper() == "POST":
                return await client.post(signed_path, content=content, headers=request_headers, extensions=extensions)
            if method.upper() == "PUT":
                return await client.put(signed_path, content=content, headers=request_headers, extensions=extensions)
            if method.upper() == "DELETE":
                if content is not None:
                    return await client.request(
                        "DELETE",
                        signed_path,
                        content=content,
                        headers=request_headers,
                        extensions=extensions,
                    )
                return await client.delete(signed_path, headers=request_headers, extensions=extensions)
            raise ValueError(f"Unsupported signed method: {method}")

        response = await _execute()
        if response.status_code >= 400 and is_expired_signature_response(response):
            offset = clock_offset_from_expired_signature(response)
            if offset is not None:
                self._clock_offset = offset
            log.warning("Delta expired_signature on %s %s — retrying once", method.upper(), signed_path)
            response = await _execute()
        return response

    async def _public_get(self, path: str, params: dict | None = None) -> dict:
        client = self._client_or_raise()
        response = await client.get(path, params=params)
        if response.status_code >= 400:
            await self._handle_error(response)
        return response.json()

    async def _signed_get(self, path: str, api_key: str, api_secret: str, params: dict | None = None) -> dict:
        response = await self._send_signed("GET", path, api_key, api_secret, params=params)
        if response.status_code >= 400:
            await self._handle_error(response)
        return response.json()

    async def _signed_post(self, path: str, api_key: str, api_secret: str, payload: dict) -> dict:
        body = json.dumps(payload, separators=(",", ":"))
        log.info("[delta] POST %s body=%s", path, body)
        response = await self._send_signed("POST", path, api_key, api_secret, content=body)
        if response.status_code >= 400:
            log.warning("[delta] POST %s -> HTTP %s: %s", path, response.status_code, response.text[:300])
            await self._handle_error(response)
        log.info("[delta] POST %s -> HTTP %s", path, response.status_code)
        return response.json()

    async def _signed_delete(
        self,
        path: str,
        api_key: str,
        api_secret: str,
        payload: dict | None = None,
    ) -> dict:
        content = json.dumps(payload, separators=(",", ":")) if payload is not None else None
        response = await self._send_signed("DELETE", path, api_key, api_secret, content=content)
        if response.status_code >= 400:
            await self._handle_error(response)
        if not response.content:
            return {}
        return response.json()

    async def _signed_put(self, path: str, api_key: str, api_secret: str, payload: dict) -> dict:
        body = json.dumps(payload, separators=(",", ":"))
        response = await self._send_signed("PUT", path, api_key, api_secret, content=body)
        if response.status_code >= 400:
            await self._handle_error(response)
        return response.json()

    async def cancel_all_entry_orders(
        self,
        api_key: str,
        api_secret: str,
        product: ProductSummary,
    ) -> None:
        """Cancel non-reduce entry/stop orders for a product (keeps reduce-only protective stops)."""
        await self.cancel_all_orders_for_product(
            api_key,
            api_secret,
            product,
            cancel_reduce_only=False,
        )

    async def cancel_all_orders_for_product(
        self,
        api_key: str,
        api_secret: str,
        product: ProductSummary,
        *,
        cancel_reduce_only: bool = True,
    ) -> None:
        """Cancel open orders for a product; optionally includes reduce-only legs."""
        await self._signed_delete(
            "/v2/orders/all",
            api_key,
            api_secret,
            {
                "product_id": product.product_id,
                "cancel_limit_orders": True,
                "cancel_stop_orders": True,
                "cancel_reduce_only_orders": cancel_reduce_only,
            },
        )

    async def fetch_profile(self, api_key: str, api_secret: str) -> DeltaProfile:
        node = await self._signed_get("/v2/profile", api_key, api_secret)
        if not node.get("success", True):
            msg = node.get("error", {}).get("message", "Delta profile validation failed.")
            raise http_error(502, msg)
        result = node.get("result", {})
        return DeltaProfile(
            id=str(result.get("id", "")),
            account_name=result.get("account_name", ""),
            email=result.get("email", ""),
            sub_account=bool(result.get("is_sub_account", False)),
        )

    async def fetch_ticker(self, symbol: str) -> InstrumentSummary:
        normalized = normalize_symbol(symbol)
        node = await self._public_get(f"/v2/tickers/{normalized}")
        result = node.get("result")
        if not isinstance(result, dict):
            raise http_error(404, f"Symbol {normalized} not found on Delta Exchange.")
        return self._map_instrument(result)

    async def fetch_tickers(
        self,
        underlying: str | None = None,
        expiry_date: str | None = None,
        contract_types: str | None = None,
    ) -> list[dict]:
        params: dict[str, str] = {}
        if underlying:
            params["underlying_asset_symbols"] = normalize_symbol(underlying)
        if expiry_date:
            params["expiry_date"] = expiry_date
        if contract_types:
            params["contract_types"] = contract_types
        node = await self._public_get("/v2/tickers", params or None)
        result = node.get("result", [])
        return result if isinstance(result, list) else []

    async def fetch_perpetual_funding_intervals(self) -> dict[str, int]:
        """Map perpetual symbol -> funding exchange interval in seconds.

        Delta's funding interval is contract-specific (1h/4h/8h) and exposed as
        ``product_specs.rate_exchange_interval`` (seconds) on the products list,
        not on the ticker feed.
        """
        intervals: dict[str, int] = {}
        after: str | None = None
        while True:
            params: dict[str, str] = {
                "states": "live",
                "page_size": "100",
                "contract_types": "perpetual_futures",
            }
            if after:
                params["after"] = after
            node = await self._public_get("/v2/products", params)
            for product in node.get("result", []):
                symbol = product.get("symbol")
                specs = product.get("product_specs") or {}
                interval = specs.get("rate_exchange_interval")
                if symbol and isinstance(interval, (int, float)) and interval > 0:
                    intervals[str(symbol)] = int(interval)
            after = node.get("meta", {}).get("after")
            if not after:
                break
        return intervals

    async def list_perpetual_symbols(self) -> list[dict[str, str]]:
        """Live perpetual symbols. Cached by callers so keystrokes do not page Delta."""
        rows: list[dict[str, str]] = []
        seen: set[str] = set()
        after: str | None = None
        while True:
            params: dict[str, str] = {
                "states": "live",
                "page_size": "100",
                "contract_types": "perpetual_futures",
            }
            if after:
                params["after"] = after
            node = await self._public_get("/v2/products", params)
            for product in node.get("result", []):
                symbol = normalize_symbol(str(product.get("symbol") or ""))
                if not symbol or symbol in seen:
                    continue
                seen.add(symbol)
                description = str(product.get("description") or symbol)
                rows.append({"symbol": symbol, "description": description})
            after = (node.get("meta") or {}).get("after")
            if not after:
                break
        rows.sort(key=lambda item: item["symbol"])
        return rows

    async def fetch_tickers_batch(self, symbols: list[str]) -> list[InstrumentSummary]:
        normalized = [normalize_symbol(symbol) for symbol in symbols if symbol]
        if not normalized:
            return []
        items: list[InstrumentSummary] = []
        for index in range(0, len(normalized), 10):
            chunk = normalized[index : index + 10]
            node = await self._public_get(f"/v2/tickers/{','.join(chunk)}")
            result = node.get("result")
            if isinstance(result, list):
                items.extend(self._map_instrument(item) for item in result)
            elif isinstance(result, dict):
                items.append(self._map_instrument(result))
        return items

    async def fetch_products_filtered(
        self,
        underlying: str | None = None,
        expiry_date: str | None = None,
        contract_types: str | None = None,
        states: str = "live",
        max_pages: int | None = None,
    ) -> list[ProductSummary]:
        items: list[ProductSummary] = []
        after: str | None = None
        pages = 0
        while True:
            params: dict[str, str] = {"states": states, "page_size": "100"}
            if after:
                params["after"] = after
            if underlying:
                params["underlying_asset_symbols"] = normalize_symbol(underlying)
            if expiry_date:
                # /v2/products filters by `expiry` (YYYY-MM-DD). `expiry_date` is for /v2/tickers.
                params["expiry"] = expiry_date
            if contract_types:
                params["contract_types"] = contract_types
            node = await self._public_get("/v2/products", params)
            for product in node.get("result", []):
                items.append(self._map_product(product))
            pages += 1
            after = node.get("meta", {}).get("after")
            if not after or (max_pages is not None and pages >= max_pages):
                break
        return items

    async def fetch_expired_option_products(
        self,
        underlying: str,
        expiry_date: str,
        *,
        max_pages: int = 25,
    ) -> list[ProductSummary]:
        return await self.fetch_products_filtered(
            underlying=underlying,
            expiry_date=expiry_date,
            contract_types="call_options,put_options",
            states="expired",
            max_pages=max_pages,
        )

    async def place_stop_order(
        self,
        api_key: str,
        api_secret: str,
        product: ProductSummary,
        side: str,
        size: float,
        stop_price: float,
        reduce_only: bool = False,
        client_order_id: str | None = None,
    ) -> OrderSummary:
        payload: dict[str, Any] = {
            "product_id": product.product_id,
            "product_symbol": product.symbol,
            "size": size,
            "side": side.lower(),
            # Stop-market: fill immediately at market on trigger (taker), matching the
            # native position brackets. A stop-limit could fail to fill on a fast move.
            "order_type": "market_order",
            "stop_order_type": "stop_loss_order",
            "stop_price": str(stop_price),
            "time_in_force": "gtc",
        }
        if reduce_only:
            payload["reduce_only"] = True
        if client_order_id:
            payload["client_order_id"] = client_order_id[:32]
        return await self.place_order(api_key, api_secret, payload)

    async def fetch_all_live_products(self) -> list[InstrumentSummary]:
        items: list[InstrumentSummary] = []
        after: str | None = None
        while True:
            params: dict[str, str] = {"states": "live", "page_size": "100"}
            if after:
                params["after"] = after
            node = await self._public_get("/v2/products", params)
            for product in node.get("result", []):
                items.append(self._map_product_to_instrument(product))
            after = node.get("meta", {}).get("after")
            if not after:
                break
        return items

    async def fetch_wallet_balances(self, api_key: str, api_secret: str) -> WalletSummary:
        node = await self.fetch_wallet_balances_payload(api_key, api_secret)
        return self._map_wallet(node)

    async def fetch_wallet_balances_payload(self, api_key: str, api_secret: str) -> dict:
        node = await self._signed_get("/v2/wallet/balances", api_key, api_secret)
        if not node.get("success", True):
            raise http_error(502, _delta_error_message(node, "Unable to fetch wallet balances."))
        return node

    def _map_wallet(self, node: dict) -> WalletSummary:
        return map_wallet_payload(node)

    async def fetch_product(self, symbol: str) -> ProductSummary:
        normalized = normalize_symbol(symbol)
        node = await self._public_get(f"/v2/products/{normalized}")
        result = node.get("result")
        if not isinstance(result, dict):
            raise http_error(404, f"Symbol {normalized} not found on Delta Exchange.")
        return self._map_product(result)

    async def fetch_open_orders(self, api_key: str, api_secret: str) -> list[OrderSummary]:
        node = await self._signed_get("/v2/orders", api_key, api_secret)
        return [self._map_order(item) for item in node.get("result", [])]

    async def fetch_orders_history(
        self,
        api_key: str,
        api_secret: str,
        *,
        page_size: int = 50,
        after: str | None = None,
    ) -> list[OrderSummary]:
        params: dict[str, str | int] = {"page_size": page_size}
        if after:
            params["after"] = after
        node = await self._signed_get("/v2/orders/history", api_key, api_secret, params)
        return [self._map_order(item) for item in node.get("result", [])]

    async def fetch_fills(
        self,
        api_key: str,
        api_secret: str,
        *,
        page_size: int = 50,
        after: str | None = None,
    ) -> list[dict[str, Any]]:
        rows, _after = await self.fetch_fills_page(api_key, api_secret, page_size=page_size, after=after)
        return rows

    async def fetch_fills_page(
        self,
        api_key: str,
        api_secret: str,
        *,
        page_size: int = 50,
        after: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, str | int] = {"page_size": page_size}
        if after:
            params["after"] = after
        node = await self._signed_get("/v2/fills", api_key, api_secret, params)
        rows = node.get("result", [])
        cursor = (node.get("meta") or {}).get("after")
        return [item for item in rows if isinstance(item, dict)], (str(cursor) if cursor else None)

    async def fetch_margined_positions(self, api_key: str, api_secret: str) -> list[dict]:
        node = await self._signed_get("/v2/positions/margined", api_key, api_secret)
        return node.get("result", [])

    async def change_leverage(
        self,
        api_key: str,
        api_secret: str,
        product_id: int,
        leverage: int,
    ) -> dict[str, Any]:
        payload = {"leverage": str(int(leverage))}
        node = await self._signed_post(
            f"/v2/products/{product_id}/orders/leverage",
            api_key,
            api_secret,
            payload,
        )
        return node.get("result", node) if isinstance(node, dict) else {}

    @staticmethod
    def max_leverage_for_product(product: ProductSummary, product_node: dict | None = None) -> int:
        """Derive max leverage from default_leverage, else initial_margin %.

        Delta exposes ``default_leverage`` (e.g. ``20``) directly. When absent we
        fall back to ``initial_margin``, which Delta reports as a **percentage**
        (e.g. ``5`` → 5% → 20x), so leverage is ``100 / initial_margin``.
        """
        node = product_node or {}
        default_lev = product.default_leverage
        if default_lev is None:
            default_lev = _parse_number_or_none(node.get("default_leverage"))
        if default_lev and default_lev >= 1:
            return int(default_lev)
        margin = product.initial_margin
        if margin is None:
            margin = _parse_number_or_none(node.get("initial_margin"))
        if margin and margin > 0:
            return max(1, int(100.0 / margin))
        return 1

    async def place_order(self, api_key: str, api_secret: str, payload: dict) -> OrderSummary:
        outgoing = dict(payload)
        if "size" in outgoing:
            outgoing["size"] = normalize_order_size(outgoing["size"])
        node = await self._signed_post("/v2/orders", api_key, api_secret, outgoing)
        return self._map_order(node.get("result", {}))

    async def cancel_order(self, api_key: str, api_secret: str, order_id: int) -> None:
        await self._signed_delete(f"/v2/orders/{order_id}", api_key, api_secret, payload=None)

    async def edit_order(
        self,
        api_key: str,
        api_secret: str,
        order_id: int,
        product_id: int,
        *,
        limit_price: float | None = None,
        stop_price: float | None = None,
        size: float | None = None,
    ) -> OrderSummary:
        payload: dict[str, Any] = {"id": int(order_id), "product_id": int(product_id)}
        if limit_price is not None:
            payload["limit_price"] = str(limit_price)
        if stop_price is not None:
            payload["stop_price"] = str(stop_price)
        if size is not None:
            payload["size"] = normalize_order_size(size)
        node = await self._signed_put("/v2/orders", api_key, api_secret, payload)
        if isinstance(node, dict) and node.get("success") is False:
            raise http_error(502, _delta_error_message(node, "Unable to edit the order."))
        result = node.get("result", {}) if isinstance(node, dict) else {}
        return self._map_order(result if isinstance(result, dict) else {})

    async def preview_order(self, api_key: str, api_secret: str, payload: dict) -> dict[str, Any]:
        outgoing = dict(payload)
        if "size" in outgoing:
            outgoing["size"] = normalize_order_size(outgoing["size"])
        node = await self._signed_post("/v2/orders/preview", api_key, api_secret, outgoing)
        if not node.get("success", True):
            raise http_error(502, _delta_error_message(node, "Unable to preview order."))
        result = node.get("result") if isinstance(node.get("result"), dict) else node
        return {
            "required_margin": _parse_number_or_none(result.get("required_margin") or result.get("margin")),
            "estimated_commission": _parse_number_or_none(
                result.get("estimated_commission") or result.get("commission")
            ),
            "margin_currency": str(result.get("margin_currency") or result.get("settling_asset") or "USD"),
            "fee_currency": str(result.get("fee_currency") or result.get("settling_asset") or "USD"),
            "commission_rate": _parse_number_or_none(result.get("commission_rate")),
            "raw": result,
        }

    async def fetch_order(self, api_key: str, api_secret: str, order_id: int) -> OrderSummary | None:
        try:
            node = await self._signed_get(f"/v2/orders/{order_id}", api_key, api_secret)
            result = node.get("result", {})
            if not result:
                return None
            return self._map_order(result)
        except Exception:
            return None

    async def place_position_bracket(
        self,
        api_key: str,
        api_secret: str,
        product: ProductSummary,
        stop_loss_price: float,
        take_profit_price: float | None = None,
        *,
        stop_trigger_method: str = DEFAULT_BRACKET_STOP_TRIGGER,
    ) -> None:
        """POST /v2/orders/bracket — SL/TP on an open position (full size, one bracket per position)."""
        payload: dict[str, Any] = {
            "product_id": product.product_id,
            "product_symbol": product.symbol,
            "stop_loss_order": {
                "order_type": "market_order",
                "stop_price": str(stop_loss_price),
            },
            "bracket_stop_trigger_method": stop_trigger_method,
        }
        if take_profit_price is not None and take_profit_price > 0:
            payload["take_profit_order"] = {
                "order_type": "market_order",
                "stop_price": str(take_profit_price),
            }
        await self._signed_post("/v2/orders/bracket", api_key, api_secret, payload)

    async def find_bracket_legs(
        self,
        api_key: str,
        api_secret: str,
        symbol: str,
    ) -> BracketLegs:
        normalized = normalize_symbol(symbol)
        legs = BracketLegs()
        for order in await self.fetch_open_orders(api_key, api_secret):
            if order.symbol != normalized:
                continue
            leg_type = (order.stop_order_type or "").lower()
            if leg_type == "stop_loss_order" and legs.stop_loss_order_id is None:
                legs.stop_loss_order_id = order.id
            elif leg_type == "take_profit_order" and legs.take_profit_order_id is None:
                legs.take_profit_order_id = order.id
        return legs

    async def amend_bracket(
        self,
        api_key: str,
        api_secret: str,
        order_id: int,
        product: ProductSummary,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        *,
        stop_trigger_method: str = DEFAULT_BRACKET_STOP_TRIGGER,
    ) -> None:
        payload: dict[str, Any] = {
            "id": order_id,
            "product_id": product.product_id,
            "product_symbol": product.symbol,
            "bracket_stop_trigger_method": stop_trigger_method,
        }
        if stop_loss is not None:
            payload["bracket_stop_loss_price"] = str(stop_loss)
        if take_profit is not None:
            payload["bracket_take_profit_price"] = str(take_profit)
        await self._signed_put("/v2/orders/bracket", api_key, api_secret, payload)

    async def place_reduce_limit(
        self,
        api_key: str,
        api_secret: str,
        product: ProductSummary,
        side: str,
        size: float,
        limit_price: float,
    ) -> OrderSummary:
        payload: dict[str, Any] = {
            "product_id": product.product_id,
            "product_symbol": product.symbol,
            "size": size,
            "side": side.lower(),
            "order_type": "limit_order",
            "limit_price": str(limit_price),
            "reduce_only": True,
            "time_in_force": "gtc",
        }
        return await self.place_order(api_key, api_secret, payload)

    async def place_limit_entry(
        self,
        api_key: str,
        api_secret: str,
        product: ProductSummary,
        side: str,
        size: float,
        limit_price: float,
    ) -> OrderSummary:
        payload: dict[str, Any] = {
            "product_id": product.product_id,
            "product_symbol": product.symbol,
            "size": size,
            "side": side.lower(),
            "order_type": "limit_order",
            "limit_price": str(limit_price),
            "time_in_force": "gtc",
        }
        return await self.place_order(api_key, api_secret, payload)

    async def place_market_reduce(
        self,
        api_key: str,
        api_secret: str,
        product: ProductSummary,
        side: str,
        size: float,
    ) -> OrderSummary:
        payload = {
            "product_id": product.product_id,
            "product_symbol": product.symbol,
            "size": size,
            "side": side.lower(),
            "order_type": "market_order",
            "reduce_only": True,
        }
        return await self.place_order(api_key, api_secret, payload)

    async def fetch_candles(
        self, symbol: str, resolution: str, start: int, end: int
    ) -> list[CandleBar]:
        node = await self._public_get(
            "/v2/history/candles",
            {
                "symbol": normalize_symbol(symbol),
                "resolution": resolution,
                "start": str(start),
                "end": str(end),
            },
        )
        bars = [
            CandleBar(
                time=int(item.get("time", 0)),
                open=_parse_number(item.get("open")),
                high=_parse_number(item.get("high")),
                low=_parse_number(item.get("low")),
                close=_parse_number(item.get("close")),
                volume=_parse_number(item.get("volume")),
            )
            for item in node.get("result", [])
        ]
        bars.sort(key=lambda bar: bar.time)
        return bars

    def _map_product_to_instrument(self, node: dict) -> InstrumentSummary:
        description = node.get("description") or node.get("contract_type") or "Delta product"
        product_id = node.get("id")
        return InstrumentSummary(
            symbol=normalize_symbol(node.get("symbol", "")),
            description=description,
            product_id=int(product_id) if product_id is not None else None,
            close_price=None,
            mark_price=None,
            best_bid=None,
            best_ask=None,
            change_24h=None,
            tick_size=_parse_number_or_none(node.get("tick_size")),
        )

    def _map_instrument(self, node: dict | None) -> InstrumentSummary:
        if not isinstance(node, dict):
            raise http_error(404, "Symbol not found on Delta Exchange.")
        description = node.get("description") or node.get("contract_type") or "Delta product"
        quotes = node.get("quotes") or {}
        return InstrumentSummary(
            symbol=normalize_symbol(node.get("symbol", "")),
            description=description,
            product_id=node.get("product_id"),
            close_price=_parse_number_or_none(node.get("close") or node.get("spot_price")),
            mark_price=_parse_number_or_none(node.get("mark_price")),
            best_bid=_parse_number_or_none(quotes.get("best_bid")),
            best_ask=_parse_number_or_none(quotes.get("best_ask")),
            change_24h=_parse_number_or_none(node.get("ltp_change_24h")),
        )

    def _map_product(self, node: dict | None) -> ProductSummary:
        if not isinstance(node, dict):
            raise http_error(404, "Symbol not found on Delta Exchange.")
        quoting = node.get("quoting_asset") or {}
        settling = node.get("settling_asset") or {}
        return ProductSummary(
            symbol=normalize_symbol(node.get("symbol", "")),
            product_id=int(node.get("id", 0)),
            contract_value=_parse_number(node.get("contract_value", "1")),
            tick_size=_parse_number_or_none(node.get("tick_size")),
            contract_unit_currency=node.get("contract_unit_currency", "USD"),
            quoting_asset=quoting.get("symbol", "USD"),
            settling_asset=settling.get("symbol") or quoting.get("symbol", "USD"),
            notional_type=str(node.get("notional_type") or "vanilla"),
            initial_margin=_parse_number_or_none(node.get("initial_margin")),
            default_leverage=_parse_number_or_none(node.get("default_leverage")),
            taker_commission_rate=_parse_number_or_none(node.get("taker_commission_rate")),
            maker_commission_rate=_parse_number_or_none(node.get("maker_commission_rate")),
            contract_type=str(node.get("contract_type") or "") or None,
            strike_price=_parse_number_or_none(node.get("strike_price") or node.get("strike")),
            expiry=str(node.get("settlement_time") or node.get("expiry") or "") or None,
            underlying_asset=str(
                (node.get("underlying_asset") or {}).get("symbol")
                or node.get("underlying_asset_symbol")
                or ""
            ).upper()
            or None,
            lot_size=_parse_number_or_none(node.get("lot_size")),
        )

    def _map_order(self, node: dict) -> OrderSummary:
        state = str(node.get("state", "")).upper()
        status_map = {"OPEN": "PENDING", "CLOSED": "CLOSED", "CANCELLED": "CANCELLED"}
        status = status_map.get(state, state or "PENDING")
        return OrderSummary(
            id=int(node.get("id", 0)),
            symbol=normalize_symbol(node.get("product_symbol", "")),
            product_id=int(node.get("product_id", 0)),
            order_type=node.get("order_type", ""),
            side=str(node.get("side", "")).upper(),
            limit_price=_parse_number_or_none(node.get("limit_price") or node.get("average_fill_price")),
            stop_price=_parse_number_or_none(node.get("stop_price")),
            take_profit_price=_parse_number_or_none(node.get("bracket_take_profit_price")),
            stop_loss_price=_parse_number_or_none(node.get("bracket_stop_loss_price")),
            size=_parse_number_or_none(node.get("size")),
            unfilled_size=_parse_number_or_none(node.get("unfilled_size")),
            status=status,
            created_at=str(node.get("created_at", "")),
            client_order_id=str(node.get("client_order_id") or "") or None,
            stop_order_type=str(node.get("stop_order_type") or "") or None,
            reduce_only=str(node.get("reduce_only", "")).lower() in {"true", "1"},
            average_fill_price=_parse_number_or_none(node.get("average_fill_price")),
        )
