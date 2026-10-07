from __future__ import annotations
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from cryptobridge.config import settings
from cryptobridge.logging_config import configure_logging
from cryptobridge.db import close_db, connect_db
from cryptobridge.delta.market_data import DeltaMarketDataService
from cryptobridge.delta.private_stream import DeltaPrivateStreamService
from cryptobridge.delta.rest_client import DeltaRestClient
from cryptobridge.mt5.client import Mt5Client
from cryptobridge.routers import accounts, auth, journal, live, market, meta, mt5_accounts, orders, positions, watchlist
from cryptobridge.services.account_service import AccountService
from cryptobridge.services.auth_service import AuthService
from cryptobridge.services.journal_service import JournalService
from cryptobridge.services.mt5_account_service import Mt5AccountService
from cryptobridge.services.mt5_price_feed import Mt5PriceFeed
from cryptobridge.services.order_service import OrderService
from cryptobridge.services.positions_service import PositionsService
from cryptobridge.services.snapshot_service import SnapshotService
from cryptobridge.services.watchlist_service import WatchlistService

configure_logging(settings)
logger = logging.getLogger(__name__)

LEGACY_COLLECTIONS = (
    "sps_setups",
    "sps_trades",
    "st_perp_trades",
    "st_perp_setups",
    "rwb_sessions",
    "candle_cache",
    "candle_cache_coverage",
    "strike_forecast_models",
    "watchlist_items",
)


async def _drop_legacy_strategy_collections(db) -> None:
    for name in LEGACY_COLLECTIONS:
        try:
            await db[name].drop()
            logger.info("Dropped legacy Mongo collection: %s", name)
        except Exception as exc:
            logger.warning("Could not drop collection %s: %s", name, exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = await connect_db()
    await _drop_legacy_strategy_collections(db)
    delta = DeltaRestClient()
    await delta.start()
    market = DeltaMarketDataService()
    auth_service = AuthService(db)
    await auth_service.ensure_indexes()
    account_service = AccountService(db, delta)
    private_stream = DeltaPrivateStreamService(account_service, delta)
    mt5_client = Mt5Client()
    mt5_account_service = Mt5AccountService(db, mt5_client)
    positions_service = PositionsService(db, delta, account_service, private_stream, market, mt5_account_service)
    order_service = OrderService(db, delta, account_service)
    snapshot_service = SnapshotService(account_service, market, delta)
    watchlist_service = WatchlistService(db, market, delta, mt5_account_service)
    journal_service = JournalService(db, delta, account_service, mt5_account_service)
    mt5_feed = Mt5PriceFeed(db, market, mt5_account_service, mt5_client)

    app.state.db = db
    app.state.delta_client = delta
    app.state.market_service = market
    app.state.private_stream_service = private_stream
    app.state.auth_service = auth_service
    app.state.account_service = account_service
    app.state.order_service = order_service
    app.state.snapshot_service = snapshot_service
    app.state.positions_service = positions_service
    app.state.mt5_account_service = mt5_account_service
    app.state.watchlist_service = watchlist_service
    app.state.journal_service = journal_service
    app.state.mt5_price_feed = mt5_feed

    await market.start()
    await positions_service.start()
    await mt5_account_service.ensure_indexes()
    await watchlist_service.ensure_indexes()
    await journal_service.ensure_indexes()
    crypto_symbols = await watchlist_service.crypto_symbols()
    if crypto_symbols:
        await market.ensure_symbols(crypto_symbols)
    mt5_feed.start()
    yield
    await mt5_feed.stop()
    await positions_service.stop()
    await private_stream.stop()
    await market.stop()
    await delta.stop()
    await close_db()


app = FastAPI(title="CryptoBridge", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(mt5_accounts.router)
app.include_router(mt5_accounts.terminals_router)
app.include_router(orders.router)
app.include_router(meta.router)
app.include_router(positions.router)
app.include_router(watchlist.router)
app.include_router(market.router)
app.include_router(journal.router)
app.include_router(live.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc.detail), "detail": str(exc.detail), "status": exc.status_code},
    )
