from __future__ import annotations
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from cryptobridge.dependencies import get_account_service, get_private_stream_service, get_user
from cryptobridge.services.account_service import AccountService
from cryptobridge.delta.private_stream import DeltaPrivateStreamService

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


class AddAccountRequest(BaseModel):
    accountName: str | None = None
    apiKey: str
    apiSecret: str
    exchange: str = "delta"


class SelectAccountRequest(BaseModel):
    accountId: str


class UpdateRiskRequest(BaseModel):
    risk_amount: float = Field(alias="riskAmount")

    model_config = {"populate_by_name": True}


class UpdateTargetRequest(BaseModel):
    targetMode: str
    targetR: float | None = None


@router.get("")
async def list_accounts(user=Depends(get_user), accounts: AccountService = Depends(get_account_service)):
    items = await accounts.list_accounts(user)
    return {"accounts": items}


@router.post("")
async def add_account(
    body: AddAccountRequest,
    user=Depends(get_user),
    accounts: AccountService = Depends(get_account_service),
):
    return await accounts.add_account(
        user,
        body.accountName,
        body.apiKey,
        body.apiSecret,
        exchange=body.exchange,
    )


@router.post("/select")
async def select_account(
    request: Request,
    body: SelectAccountRequest,
    user=Depends(get_user),
    accounts: AccountService = Depends(get_account_service),
    private_stream: DeltaPrivateStreamService = Depends(get_private_stream_service),
):
    await accounts.select_account(user, body.accountId)
    await private_stream.refresh_for_user({**user, "selectedAccountId": body.accountId})
    return {"ok": True}


@router.delete("/{account_id}")
async def delete_account(
    account_id: str,
    user=Depends(get_user),
    accounts: AccountService = Depends(get_account_service),
):
    await accounts.delete_account(user, account_id)
    return {"ok": True}


@router.patch("/{account_id}/risk")
async def update_risk(
    account_id: str,
    body: UpdateRiskRequest,
    user=Depends(get_user),
    accounts: AccountService = Depends(get_account_service),
):
    return await accounts.update_risk(user, account_id, body.risk_amount)


@router.patch("/{account_id}/target")
async def update_target(
    account_id: str,
    body: UpdateTargetRequest,
    user=Depends(get_user),
    accounts: AccountService = Depends(get_account_service),
):
    return await accounts.update_target(user, account_id, body.targetMode, body.targetR)
