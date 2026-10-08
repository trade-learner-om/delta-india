from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from cryptobridge.dependencies import get_mt5_account_service, get_order_service, get_positions_service, get_user
from cryptobridge.services.mt5_account_service import Mt5AccountService
from cryptobridge.services.order_service import OrderService
from cryptobridge.services.positions_service import PositionsService

router = APIRouter(prefix="/api/orders", tags=["orders"])


class PlaceOrderRequest(BaseModel):
    symbol: str
    order_type: str | None = Field(default="LIMIT", alias="orderType")
    side: str
    entry: float | None = None
    size: float | None = None
    quantity: float | None = None
    stop_loss: float | None = Field(None, alias="stopLoss")
    target: float | None = None
    comment: str | None = None
    venue: str | None = None

    model_config = {"populate_by_name": True}


@router.get("/active")
async def active_orders(user=Depends(get_user), orders: OrderService = Depends(get_order_service)):
    items = await orders.list_active(user)
    return {"orders": items}


@router.post("/preview")
async def preview_order(
    body: PlaceOrderRequest,
    user=Depends(get_user),
    orders: OrderService = Depends(get_order_service),
    mt5_accounts: Mt5AccountService = Depends(get_mt5_account_service),
):
    payload = body.model_dump(by_alias=True)
    if str(payload.get("venue") or user.get("selectedVenue") or "") == "forex":
        return await mt5_accounts.preview(user, payload)
    return await orders.preview(user, payload)


class PendingOrderRequest(BaseModel):
    venue: str
    account_id: str = Field(alias="accountId")
    order_id: int = Field(alias="orderId")

    model_config = {"populate_by_name": True}


class EditPendingOrderRequest(PendingOrderRequest):
    price: float
    size: float | None = None


@router.post("/pending/cancel")
async def cancel_pending_order(
    body: PendingOrderRequest,
    user=Depends(get_user),
    orders: OrderService = Depends(get_order_service),
    mt5_accounts: Mt5AccountService = Depends(get_mt5_account_service),
    positions: PositionsService = Depends(get_positions_service),
):
    if str(body.venue or "").lower() == "forex":
        await mt5_accounts.cancel_pending(user, body.account_id, body.order_id)
    else:
        await orders.cancel_on_account(user, body.account_id, body.order_id)
    await positions.publish_after_order(user)
    return {"ok": True}


@router.post("/pending/edit")
async def edit_pending_order(
    body: EditPendingOrderRequest,
    user=Depends(get_user),
    orders: OrderService = Depends(get_order_service),
    mt5_accounts: Mt5AccountService = Depends(get_mt5_account_service),
    positions: PositionsService = Depends(get_positions_service),
):
    if str(body.venue or "").lower() == "forex":
        result = await mt5_accounts.edit_pending(user, body.account_id, body.order_id, body.price, body.size)
    else:
        await orders.edit_on_account(user, body.account_id, body.order_id, body.price, body.size)
        result = {"ok": True}
    await positions.publish_after_order(user)
    return result


@router.post("")
async def place_order(
    body: PlaceOrderRequest,
    user=Depends(get_user),
    orders: OrderService = Depends(get_order_service),
    mt5_accounts: Mt5AccountService = Depends(get_mt5_account_service),
    positions: PositionsService = Depends(get_positions_service),
):
    payload = body.model_dump(by_alias=True)
    if payload.get("quantity") is not None and payload.get("size") is None:
        payload["size"] = payload["quantity"]
    if str(payload.get("venue") or user.get("selectedVenue") or "") == "forex":
        result = await mt5_accounts.place(user, payload)
    else:
        result = await orders.place(user, payload)
    await positions.publish_after_order(user)
    return result


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    user=Depends(get_user),
    orders: OrderService = Depends(get_order_service),
):
    await orders.cancel(user, order_id)
    return {"ok": True}
