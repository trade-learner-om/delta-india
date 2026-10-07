"""Live Cascade Star engine: 5-minute perp stop entry with an exchange bracket."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from cryptobridge.delta.market_data import DeltaMarketDataService
from cryptobridge.delta.rest_client import DeltaRestClient, normalize_order_size, normalize_symbol
from cryptobridge.exceptions import http_error
from cryptobridge.services.account_service import AccountService
from cryptobridge.utils.cascade_star_backtest import DEFAULT_TAKER_RATE, simulate
from cryptobridge.utils.cascade_star_strategy import (
    DEFAULT_CHOP_LENGTH,
    DEFAULT_CHOP_MAX,
    DEFAULT_SESSION_END,
    DEFAULT_SESSION_START,
    DEFAULT_TARGET_R,
    RESOLUTION_SECONDS,
    SignalDecision,
    closed_bars,
    evaluate_signal,
    parse_hhmm,
    pending_cancel_reason,
)
from cryptobridge.utils.risk_sizing import RiskSizingError, compute_position_size
from cryptobridge.utils.st_options_indicators import OhlcBar

log = logging.getLogger(__name__)

CONFIG_COLLECTION = "cascade_star_config"
TRADES_COLLECTION = "cascade_star_trades"
BACKTEST_RUNS_COLLECTION = "cascade_star_backtest_runs"
BACKTEST_RUNS_KEEP = 20
CANDLE_CHUNK_SECONDS = 2 * 24 * 60 * 60
BACKTEST_WARMUP_SECONDS = 2 * 24 * 60 * 60
IST = ZoneInfo("Asia/Kolkata")
POLL_SECONDS = 15
RESOLUTION = "5m"
CANDLE_LOOKBACK_SECONDS = 2 * 24 * 60 * 60
FILL_TIMEOUT_BARS = 5
DEFAULT_SYMBOLS = ["BTCUSD", "ETHUSD"]
ALLOWED_SYMBOLS = set(DEFAULT_SYMBOLS)
DEFAULT_DIRECTION = "SHORT"
DEFAULT_MAX_RISK = 100.0
DEFAULT_SIZING_MODE = "max_risk"
DEFAULT_LOTS = 1
STATUS_PENDING = "pending_entry"
STATUS_OPEN = "open"
STATUS_CLOSED = "closed"
STATUS_CANCELLED = "cancelled"
ACTIVE_STATUSES = (STATUS_PENDING, STATUS_OPEN)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _default_config(user_id: str) -> dict[str, Any]:
    now = _now()
    return {
        "userId": user_id,
        "enabled": False,
        "symbols": list(DEFAULT_SYMBOLS),
        "direction": DEFAULT_DIRECTION,
        "maxRisk": DEFAULT_MAX_RISK,
        "sizingMode": DEFAULT_SIZING_MODE,
        "lots": DEFAULT_LOTS,
        "chopLength": DEFAULT_CHOP_LENGTH,
        "chopMax": DEFAULT_CHOP_MAX,
        "targetR": DEFAULT_TARGET_R,
        "sessionStart": DEFAULT_SESSION_START.strftime("%H:%M"),
        "sessionEnd": DEFAULT_SESSION_END.strftime("%H:%M"),
        "fillTimeoutBars": FILL_TIMEOUT_BARS,
        "createdAt": now,
        "updatedAt": now,
    }


def config_to_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": bool(doc.get("enabled")),
        "symbols": list(doc.get("symbols") or DEFAULT_SYMBOLS),
        "direction": str(doc.get("direction") or DEFAULT_DIRECTION),
        "maxRisk": float(doc.get("maxRisk") or DEFAULT_MAX_RISK),
        "sizingMode": str(doc.get("sizingMode") or DEFAULT_SIZING_MODE),
        "lots": int(doc.get("lots") or DEFAULT_LOTS),
        "chopLength": int(doc.get("chopLength") or DEFAULT_CHOP_LENGTH),
        "chopMax": float(doc.get("chopMax") if doc.get("chopMax") is not None else DEFAULT_CHOP_MAX),
        "targetR": float(doc.get("targetR") if doc.get("targetR") is not None else DEFAULT_TARGET_R),
        "sessionStart": str(doc.get("sessionStart") or "15:30"),
        "sessionEnd": str(doc.get("sessionEnd") or "23:00"),
        "fillTimeoutBars": int(doc.get("fillTimeoutBars") or FILL_TIMEOUT_BARS),
        "resolution": RESOLUTION,
    }


def trade_to_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc.get("_id")),
        "symbol": doc.get("symbol"),
        "direction": doc.get("direction"),
        "status": doc.get("status"),
        "entry": doc.get("entry"),
        "stopLoss": doc.get("stopLoss"),
        "target": doc.get("target"),
        "r": doc.get("r"),
        "size": doc.get("size"),
        "chop": doc.get("chop"),
        "signalBarTime": doc.get("signalBarTime"),
        "entryOrderId": doc.get("entryOrderId"),
        "bracketAttached": bool(doc.get("bracketAttached")),
        "fillPrice": doc.get("fillPrice"),
        "exitReason": doc.get("exitReason"),
        "error": doc.get("error"),
        "createdAt": _iso(doc.get("createdAt")),
        "updatedAt": _iso(doc.get("updatedAt")),
        "exitTime": _iso(doc.get("exitTime")),
    }


class CascadeStarService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        delta: DeltaRestClient,
        account_service: AccountService,
        market: DeltaMarketDataService,
    ) -> None:
        self._db = db
        self._config = db[CONFIG_COLLECTION]
        self._trades = db[TRADES_COLLECTION]
        self._runs = db[BACKTEST_RUNS_COLLECTION]
        self._delta = delta
        self._accounts = account_service
        self._market = market
        self._task: asyncio.Task | None = None
        self._activity: dict[str, list[dict[str, Any]]] = {}
        self._scans: dict[str, dict[str, dict[str, Any]]] = {}
        self._backtest_jobs: dict[str, dict[str, Any]] = {}

    async def ensure_indexes(self) -> None:
        await self._config.create_index("userId", unique=True)
        await self._trades.create_index([("userId", 1), ("symbol", 1), ("status", 1)])
        await self._trades.create_index([("userId", 1), ("createdAt", -1)])
        await self._runs.create_index([("userId", 1), ("createdAt", -1)])

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop(), name="cascade-star-engine")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def meta(self) -> dict[str, Any]:
        return {
            "symbols": list(DEFAULT_SYMBOLS),
            "directions": ["SHORT", "LONG"],
            "resolution": RESOLUTION,
            "defaults": config_to_view(_default_config("")),
        }

    async def get_config(self, user: dict[str, Any]) -> dict[str, Any]:
        doc = await self._config.find_one({"userId": user["id"]})
        if not doc:
            doc = _default_config(user["id"])
            await self._config.insert_one(doc)
        return config_to_view(doc)

    async def patch_config(self, user: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        await self.get_config(user)
        updates = self._validated_updates(patch)
        updates["updatedAt"] = _now()
        await self._config.update_one({"userId": user["id"]}, {"$set": updates})
        return await self.get_config(user)

    async def start_live(self, user: dict[str, Any], patch: dict[str, Any] | None = None) -> dict[str, Any]:
        if not user.get("selectedAccountId"):
            raise http_error(400, "Select a trading account before starting Cascade Star.")
        await self.get_config(user)
        updates = self._validated_updates(patch or {})
        updates["enabled"] = True
        updates["updatedAt"] = _now()
        await self._config.update_one({"userId": user["id"]}, {"$set": updates})
        config = await self.get_config(user)
        await self._market.ensure_symbols(set(config["symbols"]))
        self._push_activity(
            user["id"],
            f"Cascade Star on · {config['direction']} · {', '.join(config['symbols'])}",
        )
        return await self.live_snapshot(user)

    async def stop_live(self, user: dict[str, Any]) -> dict[str, Any]:
        await self.get_config(user)
        await self._cancel_pending_trades(user["id"], "manual_stop")
        await self._config.update_one(
            {"userId": user["id"]},
            {"$set": {"enabled": False, "updatedAt": _now()}},
            upsert=True,
        )
        self._push_activity(user["id"], "Cascade Star turned off. Working stops were cancelled. Open brackets stay on the exchange.")
        return await self.live_snapshot(user)

    async def live_snapshot(self, user: dict[str, Any]) -> dict[str, Any]:
        config = await self.get_config(user)
        active = await self._list_trades(user["id"], statuses=ACTIVE_STATUSES)
        return {
            "config": config,
            "active": [trade_to_view(doc) for doc in active],
            "scans": self._scans.get(user["id"], {}),
            "activity": list(self._activity.get(user["id"], [])),
        }

    async def history(self, user: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]:
        capped = max(1, min(int(limit), 200))
        cursor = (
            self._trades.find({"userId": user["id"], "status": {"$in": [STATUS_CLOSED, STATUS_CANCELLED]}})
            .sort("createdAt", -1)
            .limit(capped)
        )
        return [trade_to_view(doc) async for doc in cursor]

    async def submit_backtest(self, user: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        from_raw = body.get("from") or body.get("fromDate")
        to_raw = body.get("to") or body.get("toDate")
        if not from_raw or not to_raw:
            raise http_error(400, "from and to dates are required.")
        try:
            from_date = date.fromisoformat(str(from_raw)[:10])
            to_date = date.fromisoformat(str(to_raw)[:10])
        except ValueError as exc:
            raise http_error(400, "Invalid from/to date.") from exc
        if to_date < from_date:
            raise http_error(400, "to must be on or after from.")
        current = self._backtest_jobs.get(user["id"])
        if current and current.get("status") == "processing":
            raise http_error(409, "A Cascade Star backtest is already running.")
        config = await self.get_config(user)
        settings = self._backtest_settings(config, body)
        job_id = str(uuid.uuid4())
        job = {
            "id": job_id,
            "userId": user["id"],
            "status": "processing",
            "progress": 0,
            "stage": "starting",
            "settings": settings,
            "result": None,
            "error": None,
            "runId": None,
            "createdAt": _iso(_now()),
        }
        self._backtest_jobs[user["id"]] = job
        asyncio.create_task(self._run_backtest_job(user["id"], job_id, from_date, to_date, settings), name=f"cascade-star-bt-{job_id[:8]}")
        return self._job_public(job)

    def get_backtest_job(self, user: dict[str, Any]) -> dict[str, Any] | None:
        return self._job_public(self._backtest_jobs.get(user["id"]))

    async def list_backtest_runs(self, user: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
        capped = max(1, min(int(limit), BACKTEST_RUNS_KEEP))
        cursor = self._runs.find({"userId": user["id"]}).sort("createdAt", -1).limit(capped)
        return [_run_list_item(doc) async for doc in cursor]

    async def get_backtest_run(self, user: dict[str, Any], run_id: str) -> dict[str, Any]:
        try:
            oid = ObjectId(run_id)
        except Exception as exc:
            raise http_error(400, "Invalid run id.") from exc
        doc = await self._runs.find_one({"_id": oid, "userId": user["id"]})
        if not doc:
            raise http_error(404, "Backtest run not found.")
        return _run_detail(doc)

    async def _run_backtest_job(
        self,
        user_id: str,
        job_id: str,
        from_date: date,
        to_date: date,
        settings: dict[str, Any],
    ) -> None:
        job = self._backtest_jobs.get(user_id)
        if not job or job.get("id") != job_id:
            return
        try:
            window_start, window_end = _ist_window(from_date, to_date)
            symbol = settings["symbol"]
            job["stage"] = "candles"
            job["progress"] = 5
            product = await self._delta.fetch_product(symbol)
            bars = await self._fetch_candle_chunks(
                symbol,
                window_start - BACKTEST_WARMUP_SECONDS,
                window_end,
                job,
            )
            job["stage"] = "replay"
            job["progress"] = 80
            taker = product.taker_commission_rate if product.taker_commission_rate and product.taker_commission_rate > 0 else DEFAULT_TAKER_RATE
            result = simulate(
                bars,
                direction=settings["direction"],
                tick_size=product.tick_size,
                contract_value=float(product.contract_value or 0.001),
                taker_rate=float(taker),
                sizing_mode=settings["sizingMode"],
                max_risk=float(settings["maxRisk"]),
                lots=int(settings["lots"]),
                chop_length=int(settings["chopLength"]),
                chop_max=float(settings["chopMax"]),
                target_r=float(settings["targetR"]),
                session_start=settings["sessionStart"],
                session_end=settings["sessionEnd"],
                fill_timeout_bars=int(settings["fillTimeoutBars"]),
                window_start=window_start,
                window_end=window_end,
            )
            result["symbol"] = symbol
            result["from"] = from_date.isoformat()
            result["to"] = to_date.isoformat()
            result["bars"] = len(bars)
            run_id = await self._persist_backtest_run(user_id, settings, result)
            job["status"] = "completed"
            job["progress"] = 100
            job["stage"] = "done"
            job["result"] = result
            job["runId"] = run_id
        except Exception as exc:
            log.exception("Cascade Star backtest failed user=%s", user_id)
            job["status"] = "failed"
            job["stage"] = "failed"
            job["error"] = str(exc)
            await self._persist_backtest_run(user_id, settings, None, error=str(exc))

    async def _fetch_candle_chunks(
        self,
        symbol: str,
        start: int,
        end: int,
        job: dict[str, Any],
    ) -> list[OhlcBar]:
        merged: dict[int, OhlcBar] = {}
        cursor = int(start)
        span = max(1, int(end) - int(start))
        while cursor < end:
            chunk_end = min(cursor + CANDLE_CHUNK_SECONDS, int(end))
            raw = await self._delta.fetch_candles(symbol, RESOLUTION, cursor, chunk_end)
            for candle in raw:
                merged[int(candle.time)] = OhlcBar(
                    time=int(candle.time),
                    open=float(candle.open),
                    high=float(candle.high),
                    low=float(candle.low),
                    close=float(candle.close),
                    volume=float(candle.volume or 0),
                )
            cursor = chunk_end
            done = min(1.0, (cursor - int(start)) / span)
            job["progress"] = 10 + int(65 * done)
        return [merged[key] for key in sorted(merged)]

    async def _persist_backtest_run(
        self,
        user_id: str,
        settings: dict[str, Any],
        result: dict[str, Any] | None,
        error: str | None = None,
    ) -> str:
        inserted = await self._runs.insert_one(
            {
                "userId": user_id,
                "createdAt": _now(),
                "status": "failed" if error else "completed",
                "settings": settings,
                "result": result,
                "error": error,
            }
        )
        run_id = str(inserted.inserted_id)
        keep = (
            await self._runs.find({"userId": user_id}, {"_id": 1})
            .sort("createdAt", -1)
            .limit(BACKTEST_RUNS_KEEP)
            .to_list(length=BACKTEST_RUNS_KEEP)
        )
        keep_ids = [doc["_id"] for doc in keep]
        if keep_ids:
            await self._runs.delete_many({"userId": user_id, "_id": {"$nin": keep_ids}})
        return run_id

    def _backtest_settings(self, config: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        merged = {
            "symbol": body.get("symbol") or (config.get("symbols") or DEFAULT_SYMBOLS)[0],
            "direction": body.get("direction") or config.get("direction"),
            "maxRisk": body.get("maxRisk") if body.get("maxRisk") is not None else config.get("maxRisk"),
            "sizingMode": body.get("sizingMode") or config.get("sizingMode"),
            "lots": body.get("lots") if body.get("lots") is not None else config.get("lots"),
            "chopLength": body.get("chopLength") if body.get("chopLength") is not None else config.get("chopLength"),
            "chopMax": body.get("chopMax") if body.get("chopMax") is not None else config.get("chopMax"),
            "targetR": body.get("targetR") if body.get("targetR") is not None else config.get("targetR"),
            "sessionStart": body.get("sessionStart") or config.get("sessionStart"),
            "sessionEnd": body.get("sessionEnd") or config.get("sessionEnd"),
            "fillTimeoutBars": body.get("fillTimeoutBars") if body.get("fillTimeoutBars") is not None else config.get("fillTimeoutBars"),
            "from": str(body.get("from") or body.get("fromDate") or "")[:10],
            "to": str(body.get("to") or body.get("toDate") or "")[:10],
        }
        checked = self._validated_updates(
            {
                "symbols": [merged["symbol"]],
                "direction": merged["direction"],
                "maxRisk": merged["maxRisk"],
                "sizingMode": merged["sizingMode"],
                "lots": merged["lots"],
                "chopLength": merged["chopLength"],
                "chopMax": merged["chopMax"],
                "targetR": merged["targetR"],
                "sessionStart": merged["sessionStart"],
                "sessionEnd": merged["sessionEnd"],
                "fillTimeoutBars": merged["fillTimeoutBars"],
            }
        )
        checked["symbol"] = checked.pop("symbols")[0]
        checked["from"] = merged["from"]
        checked["to"] = merged["to"]
        return checked

    def _job_public(self, job: dict[str, Any] | None) -> dict[str, Any] | None:
        if not job:
            return None
        return {
            "id": job["id"],
            "status": job["status"],
            "progress": job.get("progress", 0),
            "stage": job.get("stage"),
            "result": job.get("result"),
            "error": job.get("error"),
            "runId": job.get("runId"),
            "createdAt": job.get("createdAt"),
        }

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick_all()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Cascade Star engine tick failed")
            await asyncio.sleep(POLL_SECONDS)

    async def _tick_all(self) -> None:
        cursor = self._config.find({"enabled": True})
        async for doc in cursor:
            user_id = doc.get("userId")
            if not user_id:
                continue
            try:
                await self._tick_user(str(user_id))
            except Exception:
                log.exception("Cascade Star tick failed for user %s", user_id)

    async def _tick_user(self, user_id: str) -> None:
        config = await self.get_config({"id": user_id})
        if not config.get("enabled"):
            return
        user = await self._load_user(user_id)
        if not user.get("selectedAccountId"):
            self._push_activity(user_id, "Select a trading account. Cascade Star is waiting.")
            return
        account = await self._accounts.get_account(user_id, str(user["selectedAccountId"]))
        if not account:
            self._push_activity(user_id, "Selected trading account was not found.")
            return
        api_key, api_secret = self._accounts.credentials_for(account)
        symbols = [normalize_symbol(symbol) for symbol in config["symbols"]]
        await self._market.ensure_symbols(set(symbols))
        now = _now()
        for symbol in symbols:
            try:
                await self._tick_symbol(user_id, account, api_key, api_secret, symbol, config, now)
            except Exception:
                log.exception("Cascade Star tick failed user=%s symbol=%s", user_id, symbol)
                self._push_activity(user_id, f"{symbol}: scan failed. The next pass will try again.")

    async def _tick_symbol(
        self,
        user_id: str,
        account: dict[str, Any],
        api_key: str,
        api_secret: str,
        symbol: str,
        config: dict[str, Any],
        now: datetime,
    ) -> None:
        active = await self._active_trade(user_id, symbol)
        if active:
            await self._reconcile_trade(user_id, active, api_key, api_secret, config, now)
            active = await self._active_trade(user_id, symbol)
        if active:
            self._record_scan(user_id, symbol, {"reason": "managing", "detail": "A Cascade Star order is already working."})
            return
        await self._scan_for_entry(user_id, account, api_key, api_secret, symbol, config, now)

    async def _scan_for_entry(
        self,
        user_id: str,
        account: dict[str, Any],
        api_key: str,
        api_secret: str,
        symbol: str,
        config: dict[str, Any],
        now: datetime,
    ) -> None:
        now_unix = int(now.timestamp())
        raw = await self._delta.fetch_candles(symbol, RESOLUTION, now_unix - CANDLE_LOOKBACK_SECONDS, now_unix)
        bars = [
            OhlcBar(
                time=int(candle.time),
                open=float(candle.open),
                high=float(candle.high),
                low=float(candle.low),
                close=float(candle.close),
                volume=float(candle.volume or 0),
            )
            for candle in raw
        ]
        finished = closed_bars(bars, now_unix)
        if not finished:
            self._record_scan(user_id, symbol, {"reason": "warmup", "detail": "Waiting for a closed 5-minute candle."})
            return
        index = len(finished) - 1
        session_start = parse_hhmm(config["sessionStart"], DEFAULT_SESSION_START)
        session_end = parse_hhmm(config["sessionEnd"], DEFAULT_SESSION_END)
        decision = evaluate_signal(
            finished,
            index,
            direction=config["direction"],
            tick_size=None,
            chop_length=int(config["chopLength"]),
            chop_max=float(config["chopMax"]),
            target_r=float(config["targetR"]),
            session_start=session_start,
            session_end=session_end,
        )
        signal = finished[index]
        self._record_scan(
            user_id,
            symbol,
            {
                "reason": decision.reason,
                "detail": _decision_detail(decision),
                "barTime": signal.time,
                "chop": decision.chop,
            },
        )
        if not decision.take or decision.levels is None:
            return
        existing = await self._trades.find_one(
            {"userId": user_id, "symbol": symbol, "signalBarTime": int(signal.time)}
        )
        if existing:
            return
        product = await self._delta.fetch_product(symbol)
        levels = evaluate_signal(
            finished,
            index,
            direction=config["direction"],
            tick_size=product.tick_size,
            chop_length=int(config["chopLength"]),
            chop_max=float(config["chopMax"]),
            target_r=float(config["targetR"]),
            session_start=session_start,
            session_end=session_end,
        ).levels
        if levels is None:
            return
        try:
            size = _order_size(config, levels.entry, levels.stop, product.contract_value)
        except RiskSizingError as exc:
            await self._remember_bar(
                user_id,
                account,
                symbol,
                config,
                signal,
                levels,
                decision.chop,
                now,
                status=STATUS_CANCELLED,
                exit_reason="sizing",
                error=str(exc),
            )
            self._push_activity(user_id, f"{symbol}: {exc}")
            return
        side = "sell" if config["direction"] == "SHORT" else "buy"
        try:
            order = await self._delta.place_stop_order(
                api_key,
                api_secret,
                product,
                side,
                size,
                levels.entry,
                reduce_only=False,
                client_order_id=f"cs{user_id[-6:]}{symbol[:3]}{int(signal.time)}",
            )
        except Exception as exc:
            log.exception("Cascade Star entry failed user=%s symbol=%s", user_id, symbol)
            await self._remember_bar(
                user_id,
                account,
                symbol,
                config,
                signal,
                levels,
                decision.chop,
                now,
                status=STATUS_CANCELLED,
                exit_reason="order_rejected",
                error=str(exc),
            )
            self._push_activity(user_id, f"{symbol}: entry order was rejected.")
            return
        await self._remember_bar(
            user_id,
            account,
            symbol,
            config,
            signal,
            levels,
            decision.chop,
            now,
            status=STATUS_PENDING,
            size=size,
            entry_order_id=order.id,
        )
        self._push_activity(
            user_id,
            (
                f"{symbol}: {config['direction']} stop at {levels.entry}. "
                f"Stop {levels.stop}, target {levels.target}."
            ),
        )

    async def _reconcile_trade(
        self,
        user_id: str,
        doc: dict[str, Any],
        api_key: str,
        api_secret: str,
        config: dict[str, Any],
        now: datetime,
    ) -> None:
        symbol = str(doc.get("symbol") or "")
        direction = str(doc.get("direction") or DEFAULT_DIRECTION)
        position = await self._matching_position(api_key, api_secret, symbol, direction)
        if position is not None:
            await self._mark_open(user_id, doc, position)
            if not doc.get("bracketAttached"):
                await self._attach_bracket(user_id, doc, api_key, api_secret)
            return
        if doc.get("status") != STATUS_PENDING:
            await self._mark_finished(doc, STATUS_CLOSED, "broker_flat", now)
            self._push_activity(user_id, f"{symbol}: position is flat.")
            return
        now_unix = int(now.timestamp())
        raw = await self._delta.fetch_candles(symbol, RESOLUTION, int(doc.get("signalBarTime") or now_unix) - 60, now_unix)
        bars = [OhlcBar(time=int(candle.time), open=float(candle.open), high=float(candle.high), low=float(candle.low), close=float(candle.close)) for candle in raw]
        finished = closed_bars(bars, now_unix)
        reason = pending_cancel_reason(
            signal_bar_time=int(doc.get("signalBarTime") or 0),
            bars=finished,
            now=now,
            fill_timeout_bars=int(config.get("fillTimeoutBars") or FILL_TIMEOUT_BARS),
            session_start=parse_hhmm(str(config.get("sessionStart") or "15:30"), DEFAULT_SESSION_START),
            session_end=parse_hhmm(str(config.get("sessionEnd") or "23:00"), DEFAULT_SESSION_END),
        )
        if not reason:
            return
        await self._cancel_entry_order(api_key, api_secret, doc)
        position = await self._matching_position(api_key, api_secret, symbol, direction)
        if position is not None:
            await self._mark_open(user_id, doc, position)
            await self._attach_bracket(user_id, doc, api_key, api_secret)
            return
        await self._mark_finished(doc, STATUS_CANCELLED, reason, now)
        self._push_activity(user_id, f"{symbol}: entry cancelled ({reason.replace('_', ' ')}).")

    async def _mark_open(self, user_id: str, doc: dict[str, Any], position: tuple[float, float | None]) -> None:
        if doc.get("status") == STATUS_OPEN:
            return
        lots, fill_price = position
        was_pending = doc.get("status") == STATUS_PENDING
        doc["status"] = STATUS_OPEN
        doc["fillPrice"] = fill_price
        doc["size"] = lots
        await self._trades.update_one(
            {"_id": doc["_id"]},
            {"$set": {"status": STATUS_OPEN, "fillPrice": fill_price, "size": lots, "updatedAt": _now()}},
        )
        if was_pending:
            self._push_activity(user_id, f"{doc.get('symbol')}: stop filled. Attaching the bracket.")

    async def _attach_bracket(self, user_id: str, doc: dict[str, Any], api_key: str, api_secret: str) -> None:
        symbol = str(doc.get("symbol") or "")
        try:
            product = await self._delta.fetch_product(symbol)
            await self._delta.place_position_bracket(
                api_key,
                api_secret,
                product,
                float(doc["stopLoss"]),
                float(doc["target"]),
            )
        except Exception:
            log.exception("Cascade Star bracket failed user=%s symbol=%s", user_id, symbol)
            if not doc.get("bracketError"):
                doc["bracketError"] = True
                await self._trades.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"bracketError": True, "updatedAt": _now()}},
                )
                self._push_activity(user_id, f"{symbol}: bracket was not attached. The next pass will retry.")
            return
        doc["bracketAttached"] = True
        await self._trades.update_one(
            {"_id": doc["_id"]},
            {"$set": {"bracketAttached": True, "updatedAt": _now()}},
        )
        self._push_activity(
            user_id,
            f"{symbol}: stop {doc.get('stopLoss')} and target {doc.get('target')} are on the exchange.",
        )

    async def _cancel_pending_trades(self, user_id: str, reason: str) -> None:
        pending = await self._list_trades(user_id, statuses=(STATUS_PENDING,))
        if not pending:
            return
        user = await self._load_user(user_id)
        account_id = user.get("selectedAccountId")
        account = await self._accounts.get_account(user_id, str(account_id)) if account_id else None
        api_key = api_secret = None
        if account:
            api_key, api_secret = self._accounts.credentials_for(account)
        now = _now()
        for doc in pending:
            if api_key and api_secret:
                await self._cancel_entry_order(api_key, api_secret, doc)
            await self._mark_finished(doc, STATUS_CANCELLED, reason, now)

    async def _cancel_entry_order(self, api_key: str, api_secret: str, doc: dict[str, Any]) -> None:
        order_id = doc.get("entryOrderId")
        if not order_id:
            return
        try:
            await self._delta.cancel_order(api_key, api_secret, int(order_id))
        except Exception:
            log.exception("Cascade Star cancel failed order=%s", order_id)

    async def _mark_finished(self, doc: dict[str, Any], status: str, reason: str, now: datetime) -> None:
        await self._trades.update_one(
            {"_id": doc["_id"], "status": {"$in": list(ACTIVE_STATUSES)}},
            {"$set": {"status": status, "exitReason": reason, "exitTime": now, "updatedAt": now}},
        )

    async def _matching_position(
        self,
        api_key: str,
        api_secret: str,
        symbol: str,
        direction: str,
    ) -> tuple[float, float | None] | None:
        want = normalize_symbol(symbol)
        positions = await self._delta.fetch_margined_positions(api_key, api_secret)
        for raw in positions or []:
            if not isinstance(raw, dict):
                continue
            pos_symbol = normalize_symbol(str(raw.get("product_symbol") or raw.get("symbol") or ""))
            if pos_symbol != want:
                continue
            try:
                size = float(raw.get("size"))
            except (TypeError, ValueError):
                continue
            if direction == "SHORT" and size >= 0:
                continue
            if direction == "LONG" and size <= 0:
                continue
            raw_entry = raw.get("entry_price") or raw.get("average_entry_price") or raw.get("avg_entry_price")
            try:
                entry = float(raw_entry) if raw_entry is not None else None
            except (TypeError, ValueError):
                entry = None
            return abs(size), entry
        return None

    async def _remember_bar(
        self,
        user_id: str,
        account: dict[str, Any],
        symbol: str,
        config: dict[str, Any],
        signal: OhlcBar,
        levels,
        chop: float | None,
        now: datetime,
        *,
        status: str,
        size: int | None = None,
        entry_order_id: int | None = None,
        exit_reason: str | None = None,
        error: str | None = None,
    ) -> None:
        doc: dict[str, Any] = {
            "userId": user_id,
            "accountId": str(account.get("_id")),
            "symbol": symbol,
            "direction": config["direction"],
            "status": status,
            "signalBarTime": int(signal.time),
            "entry": levels.entry,
            "stopLoss": levels.stop,
            "target": levels.target,
            "r": levels.r,
            "tickSize": levels.tick,
            "size": size,
            "chop": chop,
            "entryOrderId": entry_order_id,
            "bracketAttached": False,
            "createdAt": now,
            "updatedAt": now,
        }
        if exit_reason:
            doc["exitReason"] = exit_reason
            doc["exitTime"] = now
        if error:
            doc["error"] = error[:500]
        await self._trades.insert_one(doc)

    async def _active_trade(self, user_id: str, symbol: str) -> dict[str, Any] | None:
        return await self._trades.find_one(
            {"userId": user_id, "symbol": normalize_symbol(symbol), "status": {"$in": list(ACTIVE_STATUSES)}}
        )

    async def _list_trades(self, user_id: str, statuses: tuple[str, ...]) -> list[dict[str, Any]]:
        cursor = self._trades.find({"userId": user_id, "status": {"$in": list(statuses)}}).sort("createdAt", -1)
        return [doc async for doc in cursor]

    async def _load_user(self, user_id: str) -> dict[str, Any]:
        doc = await self._db.app_users.find_one({"_id": ObjectId(user_id)})
        if not doc:
            raise http_error(401, "User not found")
        return {"id": str(doc["_id"]), "selectedAccountId": doc.get("selectedAccountId")}

    def _validated_updates(self, patch: dict[str, Any]) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if patch.get("symbols") is not None:
            symbols = [normalize_symbol(symbol) for symbol in patch["symbols"] if str(symbol).strip()]
            if not symbols or any(symbol not in ALLOWED_SYMBOLS for symbol in symbols):
                raise http_error(400, "symbols must be BTCUSD, ETHUSD, or both.")
            updates["symbols"] = list(dict.fromkeys(symbols))
        if patch.get("direction") is not None:
            direction = str(patch["direction"]).strip().upper()
            if direction not in {"SHORT", "LONG"}:
                raise http_error(400, "direction must be SHORT or LONG.")
            updates["direction"] = direction
        if patch.get("maxRisk") is not None:
            risk = float(patch["maxRisk"])
            if risk <= 0:
                raise http_error(400, "maxRisk must be > 0.")
            updates["maxRisk"] = risk
        if patch.get("sizingMode") is not None:
            mode = str(patch["sizingMode"]).strip().lower()
            if mode not in {"max_risk", "lots"}:
                raise http_error(400, "sizingMode must be max_risk or lots.")
            updates["sizingMode"] = mode
        if patch.get("lots") is not None:
            lots = int(patch["lots"])
            if lots < 1:
                raise http_error(400, "lots must be at least 1.")
            updates["lots"] = lots
        if patch.get("chopLength") is not None:
            length = int(patch["chopLength"])
            if length < 2:
                raise http_error(400, "chopLength must be at least 2.")
            updates["chopLength"] = length
        if patch.get("chopMax") is not None:
            chop_max = float(patch["chopMax"])
            if chop_max <= 0 or chop_max > 100:
                raise http_error(400, "chopMax must be between 0 and 100.")
            updates["chopMax"] = chop_max
        if patch.get("targetR") is not None:
            target_r = float(patch["targetR"])
            if target_r <= 0:
                raise http_error(400, "targetR must be > 0.")
            updates["targetR"] = target_r
        if patch.get("sessionStart") is not None:
            updates["sessionStart"] = _require_hhmm(patch["sessionStart"], "sessionStart")
        if patch.get("sessionEnd") is not None:
            updates["sessionEnd"] = _require_hhmm(patch["sessionEnd"], "sessionEnd")
        if patch.get("fillTimeoutBars") is not None:
            bars = int(patch["fillTimeoutBars"])
            if bars < 1:
                raise http_error(400, "fillTimeoutBars must be at least 1.")
            updates["fillTimeoutBars"] = bars
        return updates

    def _record_scan(self, user_id: str, symbol: str, payload: dict[str, Any]) -> None:
        bucket = self._scans.setdefault(user_id, {})
        bucket[symbol] = payload

    def _push_activity(self, user_id: str, message: str) -> None:
        row = {"at": _iso(_now()), "message": message}
        bucket = self._activity.setdefault(user_id, [])
        bucket.append(row)
        if len(bucket) > 40:
            del bucket[:-40]


def _ist_window(from_date: date, to_date: date) -> tuple[int, int]:
    start = datetime(from_date.year, from_date.month, from_date.day, 0, 0, tzinfo=IST)
    end = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59, tzinfo=IST)
    return int(start.timestamp()), int(end.timestamp())


def _run_list_item(doc: dict[str, Any]) -> dict[str, Any]:
    settings = doc.get("settings") or {}
    summary = (doc.get("result") or {}).get("summary") or {}
    return {
        "id": str(doc["_id"]),
        "createdAt": _iso(doc.get("createdAt")),
        "status": doc.get("status"),
        "symbol": settings.get("symbol"),
        "direction": settings.get("direction"),
        "from": settings.get("from"),
        "to": settings.get("to"),
        "netPnl": summary.get("netPnl"),
        "trades": summary.get("trades"),
        "error": doc.get("error"),
    }


def _run_detail(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "createdAt": _iso(doc.get("createdAt")),
        "status": doc.get("status"),
        "settings": doc.get("settings") or {},
        "result": doc.get("result"),
        "error": doc.get("error"),
    }


def _order_size(config: dict[str, Any], entry: float, stop: float, contract_value: float) -> int:
    if str(config.get("sizingMode") or DEFAULT_SIZING_MODE) == "lots":
        return normalize_order_size(int(config.get("lots") or DEFAULT_LOTS))
    sized = compute_position_size(float(config.get("maxRisk") or DEFAULT_MAX_RISK), entry, stop, contract_value)
    return normalize_order_size(sized)


def _decision_detail(decision: SignalDecision) -> str:
    if decision.reason == "ok":
        return "Setup is valid."
    if decision.reason == "session":
        return "The last closed candle is outside the session."
    if decision.reason == "pattern":
        return "No four-bar cascade into a rejection candle."
    if decision.reason == "warmup":
        return "Not enough closed bars for the Choppiness Index."
    if decision.reason == "chop":
        if decision.chop is None:
            return "Choppiness Index is undefined, so the bar is treated as sideways."
        return f"Choppiness Index is {decision.chop:.1f}, at or above the sideways limit."
    return decision.reason


def _require_hhmm(value: str, field: str) -> str:
    text = str(value or "").strip()
    parts = text.split(":")
    if len(parts) != 2:
        raise http_error(400, f"{field} must be HH:MM.")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise http_error(400, f"{field} must be HH:MM.") from exc
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise http_error(400, f"{field} must be HH:MM.")
    return f"{hour:02d}:{minute:02d}"
