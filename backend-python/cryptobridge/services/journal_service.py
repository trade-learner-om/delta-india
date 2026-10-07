from __future__ import annotations

import logging
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from cryptobridge.delta.rest_client import DeltaRestClient
from cryptobridge.exceptions import http_error
from cryptobridge.mt5.client import LocalMt5Error
from cryptobridge.services.account_service import AccountService
from cryptobridge.services.mt5_account_service import Mt5AccountService
from cryptobridge.utils.forex_risk import calc_rr
from cryptobridge.utils.journal_time import delta_time_to_ist, mt5_server_time_to_ist

log = logging.getLogger(__name__)
LOCK_AFTER = timedelta(hours=24)
CHART_DIR = Path(__file__).resolve().parents[2] / "data" / "journal"
ALLOWED_CHART_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


class JournalService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        delta: DeltaRestClient,
        delta_accounts: AccountService,
        mt5_accounts: Mt5AccountService,
    ) -> None:
        self._entries = db.journal_entries
        self._delta = delta
        self._delta_accounts = delta_accounts
        self._mt5_accounts = mt5_accounts
        self._contract_values: dict[str, tuple[float, float]] = {}

    async def ensure_indexes(self) -> None:
        await self._entries.create_index([("userId", 1), ("sourceTradeId", 1)], unique=True)
        await self._entries.create_index([("userId", 1), ("exitTimeIst", -1)])

    async def list_saved(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        cursor = self._entries.find({"userId": user["id"]}).sort("exitTimeIst", -1)
        docs = [doc async for doc in cursor]
        await self._repair_crypto_pnl(docs)
        return [self._public(doc) for doc in docs]

    async def recent(
        self,
        user: dict[str, Any],
        *,
        account_ids: list[str],
        from_day: str,
        to_day: str,
    ) -> list[dict[str, Any]]:
        start, end = _date_window(from_day, to_day)
        delta_accounts, mt5_accounts = await self._accounts_for(user, account_ids)
        if not delta_accounts and not mt5_accounts:
            raise http_error(400, "Select at least one account.")
        saved = {
            doc.get("sourceTradeId")
            async for doc in self._entries.find({"userId": user["id"]}, {"sourceTradeId": 1})
        }
        rows: list[dict[str, Any]] = []
        rows.extend(await self._delta_recent(delta_accounts, start))
        rows.extend(await self._mt5_recent(mt5_accounts, start, end))
        fresh = [
            row
            for row in rows
            if row.get("sourceTradeId") not in saved and _day_in_range(row.get("exitTimeIst"), start, end)
        ]
        fresh.sort(key=lambda row: row.get("exitTimeIst") or "", reverse=True)
        return fresh

    async def save(self, user: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        source_id = str(body.get("sourceTradeId") or "").strip()
        if not source_id:
            raise http_error(400, "sourceTradeId is required.")
        existing = await self._entries.find_one({"userId": user["id"], "sourceTradeId": source_id})
        if existing:
            return self._public(existing)
        match = None
        for row in await self.recent(
            user,
            account_ids=list(body.get("accountId") or body.get("accountIds") or []),
            from_day=str(body.get("from") or ""),
            to_day=str(body.get("to") or ""),
        ):
            if row.get("sourceTradeId") == source_id:
                match = row
                break
        if match is None:
            raise http_error(404, "That trade is no longer in the recent broker list.")
        now = datetime.now(timezone.utc)
        doc = {
            **match,
            "userId": user["id"],
            "setup": str(body.get("setup") or "").strip(),
            "reason": str(body.get("reason") or "").strip(),
            "chartPath": None,
            "savedAt": now,
            "updatedAt": now,
            "lockedAt": now + LOCK_AFTER,
        }
        doc.pop("id", None)
        result = await self._entries.insert_one(doc)
        doc["_id"] = result.inserted_id
        return self._public(doc)

    async def update_notes(self, user: dict[str, Any], entry_id: str, body: dict[str, Any]) -> dict[str, Any]:
        doc = await self._owned(user, entry_id)
        self._ensure_editable(doc)
        updates: dict[str, Any] = {"updatedAt": datetime.now(timezone.utc)}
        if "setup" in body:
            updates["setup"] = str(body.get("setup") or "").strip()
        if "reason" in body:
            updates["reason"] = str(body.get("reason") or "").strip()
        if "stopLoss" in body or "stop_loss" in body:
            updates["stopLoss"] = _optional_float(body.get("stopLoss", body.get("stop_loss")))
        if "target" in body:
            updates["target"] = _optional_float(body.get("target"))
        stop = updates.get("stopLoss", doc.get("stopLoss"))
        target = updates.get("target", doc.get("target"))
        updates["rr"] = calc_rr(str(doc.get("side") or ""), float(doc.get("entry") or 0), float(stop or 0), _optional_float(target))
        await self._entries.update_one({"_id": doc["_id"]}, {"$set": updates})
        doc.update(updates)
        return self._public(doc)

    async def save_chart(self, user: dict[str, Any], entry_id: str, content_type: str, data: bytes) -> dict[str, Any]:
        doc = await self._owned(user, entry_id)
        self._ensure_editable(doc)
        suffix = ALLOWED_CHART_TYPES.get(str(content_type or "").split(";")[0].strip().lower())
        if suffix is None:
            raise http_error(400, "Chart snapshot must be a PNG, JPEG, or WebP image.")
        if not data or len(data) > 5_000_000:
            raise http_error(400, "Chart snapshot must be under 5 MB.")
        CHART_DIR.mkdir(parents=True, exist_ok=True)
        path = CHART_DIR / f"{doc['_id']}{suffix}"
        path.write_bytes(data)
        await self._entries.update_one(
            {"_id": doc["_id"]},
            {"$set": {"chartPath": str(path), "chartType": content_type, "updatedAt": datetime.now(timezone.utc)}},
        )
        doc["chartPath"] = str(path)
        doc["chartType"] = content_type
        return self._public(doc)

    async def chart_file(self, user: dict[str, Any], entry_id: str) -> tuple[Path, str]:
        doc = await self._owned(user, entry_id)
        raw = doc.get("chartPath")
        if not raw:
            raise http_error(404, "This trade has no chart snapshot.")
        path = Path(raw)
        if not path.is_file():
            raise http_error(404, "Chart snapshot file is missing.")
        return path, str(doc.get("chartType") or "image/png")

    async def _accounts_for(self, user: dict[str, Any], account_ids: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        delta_accounts: list[dict[str, Any]] = []
        mt5_accounts: list[dict[str, Any]] = []
        for account_id in account_ids:
            try:
                oid = ObjectId(str(account_id))
            except Exception:
                continue
            delta = await self._delta_accounts._accounts.find_one({"_id": oid, "userId": user["id"]})
            if delta:
                delta_accounts.append(delta)
                continue
            forex = await self._mt5_accounts._accounts.find_one({"_id": oid, "userId": user["id"]})
            if forex:
                mt5_accounts.append(forex)
        return delta_accounts, mt5_accounts

    async def _delta_fills(self, api_key: str, api_secret: str, start: date) -> list[dict[str, Any]]:
        fills: list[dict[str, Any]] = []
        after: str | None = None
        for _ in range(8):
            page, after = await self._delta.fetch_fills_page(api_key, api_secret, page_size=100, after=after)
            if not page:
                break
            fills.extend(page)
            oldest = min(
                (delta_time_to_ist(item.get("created_at") or item.get("timestamp")) or "9999-99-99")[:10]
                for item in page
            )
            if not after or oldest < start.isoformat():
                break
        return fills

    async def _delta_recent(self, accounts: list[dict[str, Any]], start: date) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for account in accounts:
            try:
                api_key, api_secret = self._delta_accounts.credentials_for(account)
                fills = await self._delta_fills(api_key, api_secret, start)
            except Exception:
                log.exception("Delta fills unavailable for account %s", account.get("_id"))
                continue
            symbols = {
                str(fill.get("product_symbol") or fill.get("symbol") or "").upper()
                for fill in fills
                if fill.get("product_symbol") or fill.get("symbol")
            }
            contract_values = {symbol: await self._contract_value(symbol) for symbol in symbols}
            rows.extend(self._pair_delta_fills(account, fills, contract_values))
        return rows

    async def _mt5_recent(self, accounts: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
        start_at = datetime.combine(start, dt_time.min) - timedelta(days=1)
        end_at = datetime.combine(end, dt_time.max) + timedelta(days=1)
        rows: list[dict[str, Any]] = []
        for account in accounts:
            try:
                trades, offset = self._mt5_accounts._client.closed_trades(
                    self._mt5_accounts.credentials_for(account),
                    from_time=start_at,
                    to_time=end_at,
                )
            except LocalMt5Error as exc:
                log.info("MT5 history skipped for %s: %s", account.get("login"), exc)
                continue
            except Exception:
                log.exception("MT5 history failed for %s", account.get("login"))
                continue
            account_name = account.get("accountName") or ""
            for trade in trades:
                entry_ist = mt5_server_time_to_ist(trade.get("entryEpoch"), offset)
                exit_ist = mt5_server_time_to_ist(trade.get("exitEpoch"), offset)
                rows.append(
                    self._trade_row(
                        venue="forex",
                        account=account,
                        account_name=account_name,
                        broker_name=account.get("brokerName") or "",
                        broker_account_number=str(account.get("login") or ""),
                        currency=account.get("currency") or "USD",
                        source_timezone="mt5-server",
                        broker_offset=offset,
                        entry_time_ist=entry_ist,
                        exit_time_ist=exit_ist,
                        entry_time_raw=trade.get("entryEpoch"),
                        exit_time_raw=trade.get("exitEpoch"),
                        trade=trade,
                    )
                )
        return rows

    def _pair_delta_fills(
        self,
        account: dict[str, Any],
        fills: list[dict[str, Any]],
        contract_values: dict[str, float | None],
    ) -> list[dict[str, Any]]:
        ordered = sorted(fills, key=lambda item: str(item.get("created_at") or item.get("timestamp") or ""))
        open_by_symbol: dict[str, list[dict[str, Any]]] = {}
        closed: list[dict[str, Any]] = []
        for fill in ordered:
            symbol = str(fill.get("product_symbol") or fill.get("symbol") or "").upper()
            side = str(fill.get("side") or "").lower()
            if not symbol or side not in {"buy", "sell"}:
                continue
            book = open_by_symbol.setdefault(symbol, [])
            if book and book[0]["side"] != side:
                opened = book.pop(0)
                closed.append(self._delta_round_trip(account, opened, fill, contract_values.get(symbol)))
            else:
                book.append(fill)
        return closed

    def _delta_round_trip(
        self,
        account: dict[str, Any],
        opened: dict[str, Any],
        closed: dict[str, Any],
        contract_value: float | None,
    ) -> dict[str, Any]:
        entry = float(opened.get("price") or opened.get("fill_price") or 0)
        exit_price = float(closed.get("price") or closed.get("fill_price") or 0)
        quantity = abs(float(closed.get("size") or opened.get("size") or 0))
        side = "BUY" if str(opened.get("side") or "").lower() == "buy" else "SELL"
        commission = float(opened.get("commission") or 0) + float(closed.get("commission") or 0)
        symbol = str(closed.get("product_symbol") or opened.get("product_symbol") or "").upper()
        unit = contract_value if contract_value and contract_value > 0 else _fill_contract_value(opened, closed)
        gross, net = crypto_usd_pnl(side, entry, exit_price, quantity, unit, commission)
        source_id = str(closed.get("id") or closed.get("fill_id") or f"{opened.get('id')}:{closed.get('id')}")
        trade = {
            "sourceTradeId": f"delta:{source_id}",
            "symbol": symbol,
            "side": side,
            "entry": entry,
            "exit": exit_price,
            "quantity": quantity,
            "stopLoss": None,
            "target": None,
            "grossPnl": gross,
            "commission": round(commission, 4),
            "swap": 0.0,
            "fees": round(commission, 4),
            "netPnl": net,
            "raw": {"open": opened, "close": closed},
        }
        return self._trade_row(
            venue="crypto",
            account=account,
            account_name=account.get("accountName") or "",
            broker_name=account.get("accountName") or "Delta",
            broker_account_number=str(account.get("exchangeUserId") or ""),
            currency="USD",
            source_timezone="IST",
            broker_offset=None,
            entry_time_ist=delta_time_to_ist(opened.get("created_at") or opened.get("timestamp")),
            exit_time_ist=delta_time_to_ist(closed.get("created_at") or closed.get("timestamp")),
            entry_time_raw=opened.get("created_at") or opened.get("timestamp"),
            exit_time_raw=closed.get("created_at") or closed.get("timestamp"),
            trade=trade,
        )

    def _trade_row(
        self,
        *,
        venue: str,
        account: dict[str, Any],
        account_name: str,
        broker_name: str,
        broker_account_number: str,
        currency: str,
        source_timezone: str,
        broker_offset: int | None,
        entry_time_ist: str | None,
        exit_time_ist: str | None,
        entry_time_raw: Any,
        exit_time_raw: Any,
        trade: dict[str, Any],
    ) -> dict[str, Any]:
        stop = trade.get("stopLoss")
        target = trade.get("target")
        return {
            "venue": venue,
            "accountId": str(account.get("_id") or ""),
            "accountName": account_name,
            "brokerName": broker_name,
            "brokerAccountNumber": broker_account_number,
            "sourceTradeId": trade["sourceTradeId"],
            "symbol": trade.get("symbol"),
            "side": trade.get("side"),
            "status": "CLOSED",
            "entry": trade.get("entry"),
            "exit": trade.get("exit"),
            "quantity": trade.get("quantity"),
            "stopLoss": stop,
            "target": target,
            "rr": calc_rr(str(trade.get("side") or ""), float(trade.get("entry") or 0), float(stop or 0), float(target) if target else None),
            "grossPnl": trade.get("grossPnl"),
            "commission": trade.get("commission"),
            "swap": trade.get("swap"),
            "fees": trade.get("fees"),
            "netPnl": trade.get("netPnl"),
            "currency": currency,
            "entryTimeIst": entry_time_ist,
            "exitTimeIst": exit_time_ist,
            "entryTimeRaw": entry_time_raw,
            "exitTimeRaw": exit_time_raw,
            "sourceTimezone": source_timezone,
            "brokerUtcOffsetSeconds": broker_offset,
            "raw": trade.get("raw"),
            "setup": "",
            "reason": "",
        }

    async def _contract_value(self, symbol: str) -> float | None:
        cached = self._contract_values.get(symbol)
        if cached and time.monotonic() - cached[1] < 600:
            return cached[0]
        try:
            product = await self._delta.fetch_product(symbol)
        except Exception:
            log.info("Delta contract value unavailable for %s", symbol)
            return None
        value = float(product.contract_value or 0)
        if value <= 0:
            return None
        self._contract_values[symbol] = (value, time.monotonic())
        return value

    async def _repair_crypto_pnl(self, docs: list[dict[str, Any]]) -> None:
        symbols = {str(doc.get("symbol") or "").upper() for doc in docs if doc.get("venue") == "crypto" and doc.get("symbol")}
        units: dict[str, float] = {}
        for symbol in symbols:
            value = await self._contract_value(symbol)
            if value:
                units[symbol] = value
        for doc in docs:
            if doc.get("venue") != "crypto":
                continue
            symbol = str(doc.get("symbol") or "").upper()
            unit = units.get(symbol)
            if not unit or doc.get("entry") is None or doc.get("exit") is None:
                continue
            gross, net = crypto_usd_pnl(
                str(doc.get("side") or ""),
                float(doc.get("entry") or 0),
                float(doc.get("exit") or 0),
                float(doc.get("quantity") or 0),
                unit,
                float(doc.get("commission") or 0),
            )
            if doc.get("grossPnl") == gross and doc.get("netPnl") == net and doc.get("currency") == "USD":
                continue
            doc["grossPnl"] = gross
            doc["netPnl"] = net
            doc["currency"] = "USD"
            await self._entries.update_one(
                {"_id": doc["_id"]},
                {"$set": {"grossPnl": gross, "netPnl": net, "currency": "USD"}},
            )

    async def _owned(self, user: dict[str, Any], entry_id: str) -> dict[str, Any]:
        try:
            oid = ObjectId(entry_id)
        except Exception as exc:
            raise http_error(404, "Journal entry not found.") from exc
        doc = await self._entries.find_one({"_id": oid, "userId": user["id"]})
        if not doc:
            raise http_error(404, "Journal entry not found.")
        return doc

    @staticmethod
    def _ensure_editable(doc: dict[str, Any]) -> None:
        saved = doc.get("savedAt")
        if isinstance(saved, datetime):
            moment = saved if saved.tzinfo else saved.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) >= moment + LOCK_AFTER:
                raise http_error(409, "This journal entry can no longer be edited.")

    @staticmethod
    def _public(doc: dict[str, Any]) -> dict[str, Any]:
        saved = doc.get("savedAt")
        locked = False
        if isinstance(saved, datetime):
            moment = saved if saved.tzinfo else saved.replace(tzinfo=timezone.utc)
            locked = datetime.now(timezone.utc) >= moment + LOCK_AFTER
        return {
            "id": str(doc.get("_id") or ""),
            "venue": doc.get("venue"),
            "accountId": doc.get("accountId"),
            "accountName": doc.get("accountName"),
            "brokerName": doc.get("brokerName"),
            "brokerAccountNumber": doc.get("brokerAccountNumber"),
            "sourceTradeId": doc.get("sourceTradeId"),
            "symbol": doc.get("symbol"),
            "side": doc.get("side"),
            "status": doc.get("status"),
            "entry": doc.get("entry"),
            "exit": doc.get("exit"),
            "quantity": doc.get("quantity"),
            "stopLoss": doc.get("stopLoss"),
            "target": doc.get("target"),
            "rr": doc.get("rr"),
            "grossPnl": doc.get("grossPnl"),
            "commission": doc.get("commission"),
            "swap": doc.get("swap"),
            "fees": doc.get("fees"),
            "netPnl": doc.get("netPnl"),
            "currency": doc.get("currency"),
            "entryTimeIst": doc.get("entryTimeIst"),
            "exitTimeIst": doc.get("exitTimeIst"),
            "entryTimeRaw": doc.get("entryTimeRaw"),
            "exitTimeRaw": doc.get("exitTimeRaw"),
            "sourceTimezone": doc.get("sourceTimezone"),
            "brokerUtcOffsetSeconds": doc.get("brokerUtcOffsetSeconds"),
            "setup": doc.get("setup") or "",
            "reason": doc.get("reason") or "",
            "hasChart": bool(doc.get("chartPath")),
            "savedAt": saved.isoformat() if isinstance(saved, datetime) else saved,
            "locked": locked,
            "raw": doc.get("raw"),
        }


def crypto_usd_pnl(
    side: str,
    entry: float,
    exit_price: float,
    quantity: float,
    contract_value: float | None,
    commission: float,
) -> tuple[float, float]:
    """Dollar P/L for a Delta perpetual. Size is contracts, so price move is scaled by contract value."""
    unit = float(contract_value) if contract_value and contract_value > 0 else 1.0
    move = (exit_price - entry) if str(side or "").upper() == "BUY" else (entry - exit_price)
    gross = move * abs(float(quantity or 0)) * unit
    net = gross - abs(float(commission or 0))
    return round(gross, 4), round(net, 4)


def _fill_contract_value(opened: dict[str, Any], closed: dict[str, Any]) -> float | None:
    for fill in (closed, opened):
        raw = fill.get("contract_value")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _date_window(from_day: str, to_day: str) -> tuple[date, date]:
    try:
        start = date.fromisoformat(str(from_day or "").strip())
        end = date.fromisoformat(str(to_day or "").strip())
    except ValueError as exc:
        raise http_error(400, "Choose a from date and a to date.") from exc
    if end < start:
        raise http_error(400, "The to date must be on or after the from date.")
    return start, end


def _day_in_range(ist_iso: str | None, start: date, end: date) -> bool:
    day = str(ist_iso or "")[:10]
    return bool(day) and start.isoformat() <= day <= end.isoformat()


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
