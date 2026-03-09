from __future__ import annotations

from fastapi import APIRouter

from ..routers import ldap_guard
from ..schemas.users import UserAddRequest, UserAddResponse
from ..services.users import add_or_overwrite_user

router = APIRouter()


@router.post("", response_model=UserAddResponse)
def add_user(payload: UserAddRequest):
    return ldap_guard(lambda: add_or_overwrite_user(payload))
