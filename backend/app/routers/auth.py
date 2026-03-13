from __future__ import annotations

from fastapi import APIRouter, Depends

from ..routers.authz import get_current_user
from ..schemas.auth import ChangePasswordRequest, LoginRequest, LoginResponse
from ..services.auth_service import auth_service

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    user = auth_service.authenticate(payload.username, payload.password)
    token = auth_service.issue_token(user)
    return LoginResponse(access_token=token, user=user)


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    auth_service.authenticate(user["username"], payload.old_password)
    auth_service.update_user(user["username"], password=payload.new_password)
    return {"ok": True}

