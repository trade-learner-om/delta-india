from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from cryptobridge.dependencies import get_journal_service, get_user
from cryptobridge.services.journal_service import JournalService

router = APIRouter(prefix="/api/journal", tags=["journal"])


class SaveJournalRequest(BaseModel):
    sourceTradeId: str
    setup: str | None = None
    reason: str | None = None
    from_day: str = Field(alias="from")
    to: str
    accountId: list[str] = Field(default_factory=list)
    stopLoss: float | None = None

    model_config = {"populate_by_name": True}


class UpdateJournalRequest(BaseModel):
    setup: str | None = None
    reason: str | None = None
    stopLoss: float | None = None
    target: float | None = None


@router.get("")
async def list_journal(user=Depends(get_user), journal: JournalService = Depends(get_journal_service)):
    entries = await journal.list_saved(user)
    return {"entries": entries}


@router.get("/recent")
async def recent_trades(
    accountId: list[str] = Query(default=[]),
    from_day: str = Query(alias="from"),
    to_day: str = Query(alias="to"),
    user=Depends(get_user),
    journal: JournalService = Depends(get_journal_service),
):
    return {
        "trades": await journal.recent(user, account_ids=accountId, from_day=from_day, to_day=to_day)
    }


@router.post("")
async def save_journal(
    body: SaveJournalRequest,
    user=Depends(get_user),
    journal: JournalService = Depends(get_journal_service),
):
    return await journal.save(user, body.model_dump(by_alias=True))


@router.patch("/{entry_id}")
async def update_journal(
    entry_id: str,
    body: UpdateJournalRequest,
    user=Depends(get_user),
    journal: JournalService = Depends(get_journal_service),
):
    return await journal.update_notes(user, entry_id, body.model_dump(exclude_unset=True))


@router.post("/{entry_id}/chart")
async def upload_chart(
    entry_id: str,
    request: Request,
    user=Depends(get_user),
    journal: JournalService = Depends(get_journal_service),
):
    data = await request.body()
    return await journal.save_chart(user, entry_id, request.headers.get("content-type", ""), data)


@router.get("/{entry_id}/chart")
async def download_chart(
    entry_id: str,
    user=Depends(get_user),
    journal: JournalService = Depends(get_journal_service),
):
    path, content_type = await journal.chart_file(user, entry_id)
    return FileResponse(path, media_type=content_type)
