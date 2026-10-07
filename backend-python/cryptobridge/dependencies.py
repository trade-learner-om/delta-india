from __future__ import annotations
from fastapi import Depends, Request

from cryptobridge.delta.market_data import DeltaMarketDataService
from cryptobridge.delta.private_stream import DeltaPrivateStreamService
from cryptobridge.delta.rest_client import DeltaRestClient
from cryptobridge.services.account_service import AccountService
from cryptobridge.services.auth_service import AuthService
from cryptobridge.services.order_service import OrderService
from cryptobridge.services.positions_service import PositionsService
from cryptobridge.services.snapshot_service import SnapshotService
from cryptobridge.services.execution_engine import ExecutionEngineService
from cryptobridge.services.cascade_star_service import CascadeStarService
from cryptobridge.services.st_options_service import StOptionsService


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


def get_account_service(request: Request) -> AccountService:
    return request.app.state.account_service


def get_positions_service(request: Request) -> PositionsService:
    return request.app.state.positions_service


def get_order_service(request: Request) -> OrderService:
    return request.app.state.order_service


def get_snapshot_service(request: Request) -> SnapshotService:
    return request.app.state.snapshot_service


def get_market_service(request: Request) -> DeltaMarketDataService:
    return request.app.state.market_service


def get_private_stream_service(request: Request) -> DeltaPrivateStreamService:
    return request.app.state.private_stream_service


def get_delta_client(request: Request) -> DeltaRestClient:
    return request.app.state.delta_client


async def get_user(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
):
    return await auth.require_user_request(request)


def get_execution_engine(request: Request) -> ExecutionEngineService:
    return request.app.state.execution_engine


def get_st_options_service(request: Request) -> StOptionsService:
    return request.app.state.st_options_service


def get_cascade_star_service(request: Request) -> CascadeStarService:
    return request.app.state.cascade_star_service


def get_mt5_account_service(request: Request):
    return request.app.state.mt5_account_service


def get_watchlist_service(request: Request):
    return request.app.state.watchlist_service


def get_journal_service(request: Request):
    return request.app.state.journal_service
