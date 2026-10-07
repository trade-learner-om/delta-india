from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from passlib.context import CryptContext

from cryptobridge.exceptions import http_error

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
MAX_ACTIVE_SESSIONS = 6
IST = ZoneInfo("Asia/Kolkata")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def next_saturday_midnight_ist(now: datetime | None = None) -> datetime:
    """Next Saturday 00:00 Asia/Kolkata that is still in the future, as UTC."""
    current = _as_utc(now) or _now()
    local = current.astimezone(IST)
    days_ahead = (5 - local.weekday()) % 7
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
    if midnight <= local:
        midnight += timedelta(days=7)
    return midnight.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat()


def extract_bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return ""


class AuthService:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._users = db.app_users
        self._sessions = db.app_sessions

    async def ensure_indexes(self) -> None:
        await self._sessions.create_index("token", unique=True)
        await self._sessions.create_index([("userId", 1), ("createdAt", 1)])
        await self._sessions.create_index("expiresAt", expireAfterSeconds=0)

    async def _purge_expired_sessions(self, user_id: str) -> None:
        now = _now()
        await self._sessions.delete_many({"userId": user_id, "expiresAt": {"$lt": now}})

    async def _evict_oldest_sessions(self, user_id: str) -> None:
        cursor = self._sessions.find({"userId": user_id}).sort("createdAt", 1)
        sessions = [doc async for doc in cursor]
        overflow = len(sessions) - MAX_ACTIVE_SESSIONS + 1
        if overflow <= 0:
            return
        for doc in sessions[:overflow]:
            await self._sessions.delete_one({"_id": doc["_id"]})

    async def _create_session(self, user_id: str) -> tuple[str, datetime]:
        await self._purge_expired_sessions(user_id)
        await self._evict_oldest_sessions(user_id)
        now = _now()
        token = str(uuid.uuid4())
        expires = next_saturday_midnight_ist(now)
        await self._sessions.insert_one(
            {
                "userId": user_id,
                "token": token,
                "createdAt": now,
                "expiresAt": expires,
                "lastSeenAt": now,
            }
        )
        return token, expires

    async def _migrate_legacy_session(self, user: dict[str, Any], token: str) -> None:
        user_id = str(user["_id"])
        existing = await self._sessions.find_one({"token": token.strip()})
        if existing:
            return
        expires = _as_utc(user.get("sessionExpiresAt")) or next_saturday_midnight_ist()
        if expires < _now():
            return
        created = _as_utc(user.get("updatedAt")) or _as_utc(user.get("createdAt")) or _now()
        await self._sessions.insert_one(
            {
                "userId": user_id,
                "token": token.strip(),
                "createdAt": created,
                "expiresAt": expires,
                "lastSeenAt": _now(),
            }
        )

    async def _user_from_session(self, session: dict[str, Any]) -> dict[str, Any]:
        user = await self._users.find_one({"_id": ObjectId(session["userId"])})
        if not user:
            raise http_error(401, "Invalid session.")
        user["id"] = str(user["_id"])
        return user

    async def register(self, display_name: str, email: str, password: str) -> dict[str, str]:
        normalized = (email or "").strip().lower()
        if len(password or "") < 8:
            raise http_error(400, "Password must be at least 8 characters.")
        existing = await self._users.find_one({"email": normalized})
        if existing:
            raise http_error(400, "Email is already registered.")
        now = _now()
        doc = {
            "email": normalized,
            "displayName": (display_name or "").strip() or "CryptoBridge Operator",
            "passwordHash": pwd_context.hash(password),
            "selectedAccountId": None,
            "createdAt": now,
            "updatedAt": now,
        }
        result = await self._users.insert_one(doc)
        user_id = str(result.inserted_id)
        token, expires = await self._create_session(user_id)
        return {
            "token": token,
            "expiresAt": _iso(expires),
            "displayName": doc["displayName"],
            "email": normalized,
        }

    async def login(self, email: str, password: str) -> dict[str, str]:
        normalized = (email or "").strip().lower()
        user = await self._users.find_one({"email": normalized})
        if not user or not pwd_context.verify(password, user.get("passwordHash", "")):
            raise http_error(401, "Invalid email or password.")
        now = _now()
        user_id = str(user["_id"])
        token, expires = await self._create_session(user_id)
        await self._users.update_one({"_id": user["_id"]}, {"$set": {"updatedAt": now}})
        return {
            "token": token,
            "expiresAt": _iso(expires),
            "displayName": user.get("displayName", ""),
            "email": normalized,
        }

    async def logout(self, token: str | None) -> None:
        if not token or not token.strip():
            return
        await self._sessions.delete_one({"token": token.strip()})

    async def logout_all_except(self, token: str | None) -> int:
        if not token or not token.strip():
            raise http_error(401, "Missing token.")
        session = await self._sessions.find_one({"token": token.strip()})
        if not session:
            raise http_error(401, "Invalid session.")
        result = await self._sessions.delete_many(
            {"userId": session["userId"], "token": {"$ne": token.strip()}}
        )
        return int(result.deleted_count)

    async def require_user(self, token: str | None) -> dict[str, Any]:
        if not token or not token.strip():
            raise http_error(401, "Missing token.")
        normalized = token.strip()
        now = _now()

        session = await self._sessions.find_one({"token": normalized})
        if session:
            expires = _as_utc(session.get("expiresAt"))
            if expires and expires < now:
                await self._sessions.delete_one({"_id": session["_id"]})
                raise http_error(401, "Session expired.")
            await self._sessions.update_one(
                {"_id": session["_id"]},
                {"$set": {"lastSeenAt": now}},
            )
            return await self._user_from_session(session)

        user = await self._users.find_one({"sessionToken": normalized})
        if not user:
            raise http_error(401, "Invalid session.")
        expires = _as_utc(user.get("sessionExpiresAt"))
        if expires and expires < now:
            raise http_error(401, "Session expired.")
        await self._migrate_legacy_session(user, normalized)
        return await self._user_from_session({"userId": str(user["_id"])})

    async def require_user_request(self, request: Request) -> dict[str, Any]:
        return await self.require_user(extract_bearer_token(request))
