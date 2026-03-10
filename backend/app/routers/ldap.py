# backend/app/routers/ldap.py
from __future__ import annotations

from collections.abc import Callable
from typing import List, Optional, TypeVar

from fastapi import APIRouter, HTTPException, Query
from ldap3 import Connection
from ldap3.core.exceptions import LDAPException
from pydantic import BaseModel, Field

from app.core.settings import settings
from app.models.schema import LdapGroup, LdapUser, GroupTreeNode, OuTreeNode
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


@router.get("/health")
def health():
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


@router.get("/groups", response_model=List[LdapGroup])
def list_groups():
    return ldap_guard(lambda: get_ldap_service().list_groups())


@router.get("/users", response_model=List[LdapUser])
def list_users():
    return ldap_guard(lambda: get_ldap_service().list_users())


@router.get("/tree", response_model=List[GroupTreeNode])
def group_tree(root_group: Optional[str] = Query(default=None, description="optional root group cn")):
    return ldap_guard(lambda: get_ldap_service().build_group_tree(root_group_cn=root_group))


@router.get("/ou-tree", response_model=List[OuTreeNode])
def ou_tree():
    return ldap_guard(lambda: get_ldap_service().build_ou_tree())


@router.post("/ou", response_model=OuCreateResponse)
def create_ou(payload: OuCreateRequest):
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
):
    def _delete(svc: LdapService, conn: Connection) -> OuDeleteResponse:
        try:
            deleted_entries = svc.delete_ou(conn, ou_dn=dn, recursive=recursive)
            return OuDeleteResponse(dn=dn, recursive=recursive, deleted_entries=deleted_entries)
        except LDAPException as err:
            _raise_delete_ou_http_error(err)

    return _with_ldap_connection(_delete)


@router.patch("/ou", response_model=OuRenameResponse)
def rename_ou(payload: OuRenameRequest):
    def _rename(svc: LdapService, conn: Connection) -> OuRenameResponse:
        try:
            new_dn = svc.rename_ou(conn, ou_dn=payload.dn, new_name=payload.new_name)
            return OuRenameResponse(old_dn=payload.dn, new_dn=new_dn)
        except LDAPException as err:
            _raise_rename_ou_http_error(err)

    return _with_ldap_connection(_rename)
