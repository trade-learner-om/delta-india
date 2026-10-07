from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr

from cryptobridge.dependencies import get_auth_service, get_user
from cryptobridge.services.auth_service import AuthService, extract_bearer_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    displayName: str | None = None
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/register")
async def register(body: RegisterRequest, auth: AuthService = Depends(get_auth_service)):
    return await auth.register(body.displayName or "", str(body.email), body.password)


@router.post("/login")
async def login(body: LoginRequest, auth: AuthService = Depends(get_auth_service)):
    return await auth.login(str(body.email), body.password)


@router.post("/logout")
async def logout(request: Request, auth: AuthService = Depends(get_auth_service)):
    await auth.logout(extract_bearer_token(request))
    return {"ok": True}


@router.post("/logout-all")
async def logout_all(request: Request, auth: AuthService = Depends(get_auth_service)):
    revoked = await auth.logout_all_except(extract_bearer_token(request))
    return {"ok": True, "revoked": revoked}


@router.get("/me")
async def me(user=Depends(get_user)):
    return {
        "displayName": user.get("displayName"),
        "email": user.get("email"),
        "selectedAccountId": user.get("selectedAccountId"),
        "selectedVenue": user.get("selectedVenue"),
    }
