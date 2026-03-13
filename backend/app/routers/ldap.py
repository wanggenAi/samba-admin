# backend/app/routers/ldap.py
from __future__ import annotations

from collections.abc import Callable
from typing import List, Literal, Optional, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query
from ldap3 import Connection
from ldap3.core.exceptions import LDAPException
from pydantic import BaseModel, Field

from app.core.settings import settings
from app.schemas.ldap import GroupTreeNode, LdapGroup, LdapUser, OuTreeNode
from app.routers.authz import require_permission
from app.routers import ldap_guard
from app.services import get_ldap_service
from app.services.ldap_service import LdapService

router = APIRouter()
T = TypeVar("T")


def _with_ldap_connection(fn: Callable[[LdapService, Connection], T]) -> T:
    def _run() -> T:
        svc = get_ldap_service()
        with svc.connection() as conn:
            return fn(svc, conn)

    return ldap_guard(_run)


def _raise_create_ou_http_error(err: LDAPException) -> None:
    msg = str(err)
    if "parent DN not found" in msg:
        raise HTTPException(status_code=400, detail=msg)
    raise HTTPException(status_code=400, detail=f"create OU failed: {msg}")


def _raise_delete_ou_http_error(err: LDAPException) -> None:
    msg = str(err)
    if "recursive delete required" in msg:
        raise HTTPException(status_code=409, detail=msg)
    if "not found" in msg:
        raise HTTPException(status_code=404, detail=msg)
    if "cannot delete base DN" in msg:
        raise HTTPException(status_code=400, detail=msg)
    raise HTTPException(status_code=400, detail=f"delete OU failed: {msg}")


def _raise_rename_ou_http_error(err: LDAPException) -> None:
    msg = str(err)
    if "target DN already exists" in msg:
        raise HTTPException(status_code=409, detail=msg)
    if "insufficient access rights" in msg:
        raise HTTPException(status_code=403, detail=msg)
    if "not found" in msg:
        raise HTTPException(status_code=404, detail=msg)
    if "cannot rename base DN" in msg:
        raise HTTPException(status_code=400, detail=msg)
    raise HTTPException(status_code=400, detail=f"rename OU failed: {msg}")


class OuCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    parent_dn: Optional[str] = None


class OuCreateResponse(BaseModel):
    ok: bool = True
    dn: str
    created: bool


class OuDeleteResponse(BaseModel):
    ok: bool = True
    dn: str
    recursive: bool
    deleted_entries: int


class OuRenameRequest(BaseModel):
    dn: str = Field(min_length=1)
    new_name: str = Field(min_length=1, max_length=128)


class OuRenameResponse(BaseModel):
    ok: bool = True
    old_dn: str
    new_dn: str


class UserGroupMapItem(BaseModel):
    user_dn: str
    groups: List[str] = Field(default_factory=list)


class LdapUserPageItem(LdapUser):
    groups: List[str] = Field(default_factory=list)


class LdapUsersPageResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[LdapUserPageItem] = Field(default_factory=list)


class LdapDashboardSummaryResponse(BaseModel):
    total_users: int
    recent_login_users: int


@router.get("/health")
def health(_: dict = Depends(require_permission("dashboard.view"))):
    def _run():
        svc = get_ldap_service()
        svc.ping()
        return {
            "ok": True,
            "host": settings.ldap.host,
            "port": settings.ldap.port,
            "use_ssl": settings.ldap.use_ssl,
            "start_tls": settings.ldap.start_tls,
            "base_dn": settings.ldap.base_dn,
        }

    return ldap_guard(_run)


@router.get("/groups", response_model=List[LdapGroup], response_model_exclude_none=True, response_model_exclude_defaults=True)
def list_groups(
    include_members: bool = Query(default=True, description="include group member DN list"),
    include_description: bool = Query(default=True, description="include group description"),
    _: dict = Depends(require_permission("users.view")),
):
    return ldap_guard(
        lambda: get_ldap_service().list_groups(
            include_members=include_members,
            include_description=include_description,
        )
    )


@router.get("/users/{username}/groups", response_model=List[LdapGroup], response_model_exclude_none=True, response_model_exclude_defaults=True)
def list_user_groups(
    username: str,
    _: dict = Depends(require_permission("users.view")),
):
    def _list(svc: LdapService, conn: Connection) -> List[LdapGroup]:
        user_dn = svc.find_user_dn(conn, username.strip())
        if not user_dn:
            raise HTTPException(status_code=404, detail=f"user not found: {username}")
        groups = svc.list_user_groups(conn, user_dn=user_dn)
        groups.sort(key=lambda g: (g.cn or "").lower())
        return groups

    return _with_ldap_connection(_list)


@router.get("/user-group-map", response_model=List[UserGroupMapItem], response_model_exclude_none=True)
def user_group_map(_: dict = Depends(require_permission("users.view"))):
    def _run() -> List[UserGroupMapItem]:
        mapping = get_ldap_service().build_user_group_map()
        items = [UserGroupMapItem(user_dn=dn, groups=groups) for dn, groups in mapping.items()]
        items.sort(key=lambda x: x.user_dn)
        return items

    return ldap_guard(_run)


@router.get("/users", response_model=List[LdapUser], response_model_exclude_none=True)
def list_users(
    view: Literal["full", "list", "dashboard", "tree"] = Query(
        default="full",
        description="field set profile for user payload size",
    ),
    _: dict = Depends(require_permission("users.view")),
):
    return ldap_guard(lambda: get_ldap_service().list_users(view=view))


@router.get("/users-page", response_model=LdapUsersPageResponse, response_model_exclude_none=True)
def list_users_page(
    view: Literal["full", "list", "dashboard", "tree"] = Query(default="list"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    keyword: Optional[str] = Query(default=None),
    ou_dn: List[str] = Query(default_factory=list),
    ou_scope: Literal["direct", "subtree"] = Query(default="direct"),
    group_cn: List[str] = Query(default_factory=list),
    login_from_ms: Optional[int] = Query(default=None, ge=0),
    login_to_ms: Optional[int] = Query(default=None, ge=0),
    _: dict = Depends(require_permission("users.view")),
):
    payload = ldap_guard(
        lambda: get_ldap_service().list_users_page(
            view=view,
            page=page,
            page_size=page_size,
            keyword=keyword,
            ou_dns=ou_dn,
            ou_scope=ou_scope,
            group_cns=group_cn,
            login_from_ms=login_from_ms,
            login_to_ms=login_to_ms,
        )
    )
    return LdapUsersPageResponse(**payload)


@router.get("/dashboard-summary", response_model=LdapDashboardSummaryResponse)
def dashboard_summary(
    recent_window_days: int = Query(default=3, ge=1, le=90),
    _: dict = Depends(require_permission("dashboard.view")),
):
    payload = ldap_guard(
        lambda: get_ldap_service().dashboard_summary(recent_window_days=recent_window_days)
    )
    return LdapDashboardSummaryResponse(**payload)


@router.get("/tree", response_model=List[GroupTreeNode])
def group_tree(
    root_group: Optional[str] = Query(default=None, description="optional root group cn"),
    _: dict = Depends(require_permission("users.view")),
):
    return ldap_guard(lambda: get_ldap_service().build_group_tree(root_group_cn=root_group))


@router.get("/ou-tree", response_model=List[OuTreeNode], response_model_exclude_none=True)
def ou_tree(
    include_users: bool = Query(default=True, description="include user nodes under OUs"),
    user_view: Literal["full", "list", "dashboard", "tree"] = Query(
        default="full",
        description="user field profile when include_users=true",
    ),
    _: dict = Depends(require_permission("ous.view")),
):
    return ldap_guard(lambda: get_ldap_service().build_ou_tree(include_users=include_users, user_view=user_view))


@router.post("/ou", response_model=OuCreateResponse)
def create_ou(payload: OuCreateRequest, _: dict = Depends(require_permission("ous.create"))):
    def _create(svc: LdapService, conn: Connection) -> OuCreateResponse:
        try:
            dn, created = svc.create_ou(conn, name=payload.name, parent_dn=payload.parent_dn)
            return OuCreateResponse(dn=dn, created=created)
        except LDAPException as err:
            _raise_create_ou_http_error(err)

    return _with_ldap_connection(_create)


@router.delete("/ou", response_model=OuDeleteResponse)
def delete_ou(
    dn: str = Query(..., description="OU DN to delete"),
    recursive: bool = Query(default=False, description="delete subtree recursively"),
    _: dict = Depends(require_permission("ous.delete")),
):
    def _delete(svc: LdapService, conn: Connection) -> OuDeleteResponse:
        try:
            deleted_entries = svc.delete_ou(conn, ou_dn=dn, recursive=recursive)
            return OuDeleteResponse(dn=dn, recursive=recursive, deleted_entries=deleted_entries)
        except LDAPException as err:
            _raise_delete_ou_http_error(err)

    return _with_ldap_connection(_delete)


@router.patch("/ou", response_model=OuRenameResponse)
def rename_ou(payload: OuRenameRequest, _: dict = Depends(require_permission("ous.rename"))):
    def _rename(svc: LdapService, conn: Connection) -> OuRenameResponse:
        try:
            new_dn = svc.rename_ou(conn, ou_dn=payload.dn, new_name=payload.new_name)
            return OuRenameResponse(old_dn=payload.dn, new_dn=new_dn)
        except LDAPException as err:
            _raise_rename_ou_http_error(err)

    return _with_ldap_connection(_rename)
