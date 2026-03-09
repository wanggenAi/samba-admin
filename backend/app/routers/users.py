from __future__ import annotations

from fastapi import APIRouter

from ..routers import ldap_guard
from ..schemas.users import UserAddRequest, UserAddResponse, UserDeleteResponse
from ..services.users import add_or_overwrite_user, delete_user_by_username

router = APIRouter()


@router.post("", response_model=UserAddResponse)
def add_user(payload: UserAddRequest):
    return ldap_guard(lambda: add_or_overwrite_user(payload))


@router.delete("/{username}", response_model=UserDeleteResponse)
def delete_user(username: str):
    return ldap_guard(lambda: delete_user_by_username(username))
