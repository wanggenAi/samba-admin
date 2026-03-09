# backend/app/routers/ldap.py
from __future__ import annotations

from fastapi import APIRouter, Query
from typing import List, Optional

from app.core.settings import settings
from app.models.schema import LdapGroup, LdapUser, GroupTreeNode
from app.routers import ldap_guard
from app.services import get_ldap_service

router = APIRouter()


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
