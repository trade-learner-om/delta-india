from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from cryptobridge.dependencies import get_mt5_account_service, get_user
from cryptobridge.mt5.terminal_detection import find_running_terminal_paths, find_running_terminal_processes
from cryptobridge.services.mt5_account_service import Mt5AccountService

router = APIRouter(prefix="/api/mt5/accounts", tags=["mt5-accounts"])
terminals_router = APIRouter(prefix="/api/mt5", tags=["mt5"])


class AddMt5AccountRequest(BaseModel):
    login: str
    password: str
    server: str
    terminalPath: str = Field(alias="terminalPath")
    riskAmount: float | None = None

    model_config = {"populate_by_name": True}


class SelectAccountRequest(BaseModel):
    accountId: str


class UpdateRiskRequest(BaseModel):
    riskAmount: float = Field(alias="riskAmount")

    model_config = {"populate_by_name": True}


@terminals_router.get("/terminals")
async def list_running_terminals(user=Depends(get_user)):
    del user
    processes = await asyncio.to_thread(find_running_terminal_processes)
    path_counts: dict[str, int] = {}
    for process in processes:
        path = str(process.get("path") or "")
        if path:
            path_counts[path] = path_counts.get(path, 0) + 1
    unique = await asyncio.to_thread(find_running_terminal_paths)
    return {
        "terminals": [
            {
                "pid": process.get("pid"),
                "path": process.get("path"),
                "samePathInstanceCount": path_counts.get(str(process.get("path") or ""), 0),
            }
            for process in processes
        ],
        "uniquePaths": unique,
        "requiresUniqueInstallPaths": any(count > 1 for count in path_counts.values()),
    }


@router.get("")
async def list_mt5_accounts(user=Depends(get_user), accounts: Mt5AccountService = Depends(get_mt5_account_service)):
    return {"accounts": await accounts.list_accounts(user)}


@router.post("")
async def add_mt5_account(
    body: AddMt5AccountRequest,
    user=Depends(get_user),
    accounts: Mt5AccountService = Depends(get_mt5_account_service),
):
    return await accounts.add_account(
        user,
        login=body.login,
        password=body.password,
        server=body.server,
        terminal_path=body.terminalPath,
        risk_amount=body.riskAmount,
    )


@router.post("/select")
async def select_mt5_account(
    body: SelectAccountRequest,
    user=Depends(get_user),
    accounts: Mt5AccountService = Depends(get_mt5_account_service),
):
    await accounts.select_account(user, body.accountId)
    return {"ok": True}


@router.patch("/{account_id}/risk")
async def update_mt5_risk(
    account_id: str,
    body: UpdateRiskRequest,
    user=Depends(get_user),
    accounts: Mt5AccountService = Depends(get_mt5_account_service),
):
    return await accounts.update_risk(user, account_id, body.riskAmount)


@router.delete("/{account_id}")
async def delete_mt5_account(
    account_id: str,
    user=Depends(get_user),
    accounts: Mt5AccountService = Depends(get_mt5_account_service),
):
    await accounts.delete_account(user, account_id)
    return {"ok": True}
