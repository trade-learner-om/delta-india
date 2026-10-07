from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from cryptobridge.utils.forex_risk import normalize_price_to_symbol, normalize_volume_to_risk

log = logging.getLogger(__name__)

_SYMBOL_FILLING_FOK = 1
_SYMBOL_FILLING_IOC = 2
_SYMBOL_FILLING_RETURN = 4


class LocalMt5Error(RuntimeError):
    pass


def _load_mt5():
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise LocalMt5Error(
            "MetaTrader 5 runs on the Windows machine that hosts the terminal."
        ) from exc
    return mt5


def _filling_mode(mt5, info) -> int:
    fok = getattr(mt5, "ORDER_FILLING_FOK", 0)
    ioc = getattr(mt5, "ORDER_FILLING_IOC", 1)
    ret = getattr(mt5, "ORDER_FILLING_RETURN", 2)
    try:
        mask = int(getattr(info, "filling_mode", 0) or 0)
    except (TypeError, ValueError):
        mask = 0
    if mask & getattr(mt5, "SYMBOL_FILLING_FOK", _SYMBOL_FILLING_FOK):
        return fok
    if mask & getattr(mt5, "SYMBOL_FILLING_IOC", _SYMBOL_FILLING_IOC):
        return ioc
    return ret


def _symbol_spec(info) -> dict[str, Any]:
    data = info._asdict()
    return {
        "point": float(data.get("point") or 0),
        "tickSize": float(data.get("trade_tick_size") or data.get("point") or 0),
        "digits": int(data.get("digits") or 0),
        "contractSize": float(data.get("trade_contract_size") or 0),
        "volumeStep": float(data.get("volume_step") or 0.01),
        "volumeMin": float(data.get("volume_min") or 0.01),
        "volumeMax": float(data.get("volume_max") or 100),
        "tickValue": float(data.get("trade_tick_value") or 0),
    }


def _last_error(mt5, default: str) -> str:
    try:
        code, message = mt5.last_error()
    except Exception:
        return default
    return f"{default} ({code}: {message})"


class Mt5Client:
    """Local MetaTrader 5 terminal. The package only works on Windows beside terminal64.exe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_key: tuple[str, str, str] | None = None

    def _call(self, credentials: dict[str, str], operation: Callable[[Any], Any]) -> Any:
        mt5 = _load_mt5()
        login = str(credentials.get("login") or "").strip()
        password = str(credentials.get("password") or "")
        server = str(credentials.get("server") or "").strip()
        path = str(credentials.get("path") or "").strip()
        if not login or not password or not server or not path:
            raise LocalMt5Error("MT5 login, password, server, and terminal path are required.")
        key = (login, server, path)
        with self._lock:
            if self._active_key != key:
                mt5.shutdown()
                ok = mt5.initialize(path=path, login=int(login), password=password, server=server)
                if not ok:
                    self._active_key = None
                    raise LocalMt5Error(_last_error(mt5, "Could not open the MT5 terminal."))
                self._active_key = key
            return operation(mt5)

    def account_snapshot(self, credentials: dict[str, str]) -> dict[str, Any]:
        def operation(mt5):
            info = mt5.account_info()
            if info is None:
                raise LocalMt5Error(_last_error(mt5, "MT5 account information is unavailable."))
            data = info._asdict()
            offset = self._offset_seconds(mt5)
            return {
                "name": str(data.get("name") or ""),
                "company": str(data.get("company") or ""),
                "login": str(data.get("login") or credentials.get("login") or ""),
                "server": str(data.get("server") or credentials.get("server") or ""),
                "balance": float(data.get("balance") or 0),
                "equity": float(data.get("equity") or 0),
                "currency": str(data.get("currency") or "USD"),
                "brokerUtcOffsetSeconds": offset,
            }

        return self._call(credentials, operation)

    def symbol_tick(self, credentials: dict[str, str], symbol: str) -> dict[str, Any] | None:
        def operation(mt5):
            name = self._resolve_symbol(mt5, symbol)
            if not mt5.symbol_select(name, True):
                return None
            tick = mt5.symbol_info_tick(name)
            info = mt5.symbol_info(name)
            if tick is None:
                return None
            bid = float(tick.bid or 0)
            ask = float(tick.ask or 0)
            last = float(tick.last or 0) or ((bid + ask) / 2 if bid and ask else bid or ask)
            return {
                "symbol": name,
                "bid": bid or None,
                "ask": ask or None,
                "last": last or None,
                "time": int(getattr(tick, "time", 0) or 0),
                "digits": int(getattr(info, "digits", 0) or 0) if info is not None else None,
            }

        return self._call(credentials, operation)

    def symbol_spec(self, credentials: dict[str, str], symbol: str) -> dict[str, Any]:
        def operation(mt5):
            name = self._resolve_symbol(mt5, symbol)
            info = mt5.symbol_info(name)
            if info is None:
                raise LocalMt5Error(_last_error(mt5, f"No MT5 symbol specification for {symbol}."))
            spec = _symbol_spec(info)
            spec["symbol"] = name
            return spec

        return self._call(credentials, operation)

    def place_order(self, credentials: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
        def operation(mt5):
            symbol = self._resolve_symbol(mt5, str(payload["symbol"]))
            info = mt5.symbol_info(symbol)
            if info is None:
                raise LocalMt5Error(_last_error(mt5, f"No MT5 symbol specification for {symbol}."))
            mt5.symbol_select(symbol, True)
            spec = _symbol_spec(info)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                raise LocalMt5Error(_last_error(mt5, f"No tick available for {symbol}."))
            side = str(payload.get("side") or "").upper()
            order_type = str(payload.get("order_type") or payload.get("orderType") or "MARKET").upper()
            volume = normalize_volume_to_risk(
                float(payload["quantity"]),
                volume_step=float(spec["volumeStep"]),
                volume_min=float(spec["volumeMin"]),
                volume_max=float(spec["volumeMax"]),
            )
            if volume <= 0:
                raise LocalMt5Error("Order size is below the broker minimum.")
            if order_type == "MARKET":
                mt5_type = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL
                price = float(tick.ask if side == "BUY" else tick.bid)
                action = mt5.TRADE_ACTION_DEAL
            elif order_type == "SL":
                mt5_type = mt5.ORDER_TYPE_BUY_STOP if side == "BUY" else mt5.ORDER_TYPE_SELL_STOP
                price = float(payload["entry"])
                action = mt5.TRADE_ACTION_PENDING
            else:
                mt5_type = mt5.ORDER_TYPE_BUY_LIMIT if side == "BUY" else mt5.ORDER_TYPE_SELL_LIMIT
                price = float(payload["entry"])
                action = mt5.TRADE_ACTION_PENDING
            request = {
                "action": action,
                "symbol": symbol,
                "volume": volume,
                "type": mt5_type,
                "price": normalize_price_to_symbol(price, spec),
                "sl": normalize_price_to_symbol(float(payload.get("stop_loss") or payload.get("stopLoss") or 0), spec),
                "tp": normalize_price_to_symbol(float(payload.get("target") or 0), spec),
                "deviation": 20,
                "magic": 20261007,
                "comment": "ledger",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": _filling_mode(mt5, info),
            }
            result = mt5.order_send(request)
            if result is None:
                raise LocalMt5Error(_last_error(mt5, "MT5 order_send returned no result."))
            data = result._asdict()
            if data.get("retcode") not in {mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED}:
                raise LocalMt5Error(
                    f"MT5 order rejected: retcode={data.get('retcode')} comment={data.get('comment')}"
                )
            return {
                "orderId": str(data.get("order") or ""),
                "dealId": str(data.get("deal") or ""),
                "volume": volume,
                "price": request["price"],
                "symbol": symbol,
                "retcode": data.get("retcode"),
                "raw": {key: data.get(key) for key in ("retcode", "order", "deal", "volume", "price", "comment")},
            }

        return self._call(credentials, operation)

    def closed_trades(self, credentials: dict[str, str], *, days: int = 30) -> tuple[list[dict[str, Any]], int]:
        def operation(mt5):
            offset = self._offset_seconds(mt5)
            to_time = datetime.now(timezone.utc) + timedelta(seconds=offset)
            from_time = to_time - timedelta(days=max(1, days))
            deals = mt5.history_deals_get(from_time, to_time) or []
            return self._closed_rows(mt5, deals), offset

        return self._call(credentials, operation)

    @staticmethod
    def _offset_seconds(mt5) -> int:
        utc_now = int(datetime.now(timezone.utc).timestamp())
        tick = None
        for symbol in ("EURUSD", "XAUUSD", "BTCUSD"):
            info = mt5.symbol_info_tick(symbol)
            if info is not None and int(getattr(info, "time", 0) or 0) > 0:
                tick = info
                break
        if tick is None:
            return 0
        return int(getattr(tick, "time", 0) or 0) - utc_now

    @staticmethod
    def _resolve_symbol(mt5, requested: str) -> str:
        name = str(requested or "").strip()
        info = mt5.symbol_info(name)
        if info is not None:
            return str(info.name)
        upper = name.upper()
        for item in mt5.symbols_get() or []:
            candidate = str(getattr(item, "name", "") or "")
            if candidate.upper() == upper or candidate.upper().startswith(upper):
                return candidate
        raise LocalMt5Error(f"Symbol {requested} is not on this MT5 terminal.")

    @staticmethod
    def _closed_rows(mt5, deals) -> list[dict[str, Any]]:
        entry_in = getattr(mt5, "DEAL_ENTRY_IN", 0)
        entry_out = getattr(mt5, "DEAL_ENTRY_OUT", 1)
        entry_inout = getattr(mt5, "DEAL_ENTRY_INOUT", 2)
        type_buy = getattr(mt5, "DEAL_TYPE_BUY", 0)
        groups: dict[str, list[dict]] = {}
        for deal in deals:
            data = deal._asdict() if hasattr(deal, "_asdict") else dict(deal)
            if int(data.get("entry") if data.get("entry") is not None else -1) not in {entry_in, entry_out, entry_inout}:
                continue
            if int(data.get("type") if data.get("type") is not None else -1) not in {type_buy, getattr(mt5, "DEAL_TYPE_SELL", 1)}:
                continue
            position_id = str(data.get("position_id") or data.get("position") or "")
            if not position_id:
                continue
            groups.setdefault(position_id, []).append(data)
        rows: list[dict[str, Any]] = []
        for position_id, items in groups.items():
            ordered = sorted(items, key=lambda item: int(item.get("time") or 0))
            opens = [item for item in ordered if int(item.get("entry") or -1) in {entry_in, entry_inout}]
            closes = [item for item in ordered if int(item.get("entry") or -1) in {entry_out, entry_inout}]
            if not opens or not closes:
                continue
            opened = opens[0]
            for closed in closes:
                if closed is opened and int(closed.get("entry") or -1) != entry_inout:
                    continue
                side = "BUY" if int(opened.get("type") or 0) == type_buy else "SELL"
                profit = float(closed.get("profit") or 0)
                commission = float(closed.get("commission") or 0) + float(closed.get("fee") or 0)
                swap = float(closed.get("swap") or 0)
                rows.append(
                    {
                        "sourceTradeId": f"mt5:{position_id}:{closed.get('ticket')}",
                        "positionId": position_id,
                        "orderId": str(closed.get("order") or ""),
                        "dealIds": [str(opened.get("ticket") or ""), str(closed.get("ticket") or "")],
                        "symbol": str(opened.get("symbol") or closed.get("symbol") or "").upper(),
                        "side": side,
                        "entry": float(opened.get("price") or 0),
                        "exit": float(closed.get("price") or 0),
                        "quantity": float(closed.get("volume") or opened.get("volume") or 0),
                        "stopLoss": float(closed.get("sl") or opened.get("sl") or 0) or None,
                        "target": float(closed.get("tp") or opened.get("tp") or 0) or None,
                        "grossPnl": round(profit, 2),
                        "commission": round(commission, 2),
                        "swap": round(swap, 2),
                        "fees": round(commission, 2),
                        "netPnl": round(profit + commission + swap, 2),
                        "entryEpoch": int(opened.get("time") or 0),
                        "exitEpoch": int(closed.get("time") or 0),
                        "raw": {"open": opened, "close": closed},
                    }
                )
        return rows
