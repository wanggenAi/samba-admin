# backend/app/routers/ldap.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from app.core.settings import settings
from app.models.schema import LdapGroup, LdapUser, GroupTreeNode
from app.services.ldap_service import LdapService

router = APIRouter()


def _service() -> LdapService:
    cfg = settings.ldap
    if not cfg.bind_password:
        raise HTTPException(status_code=400, detail="LDAP_BIND_PASSWORD is empty (set env).")
    return LdapService(cfg)


@router.get("/health")
def health():
    try:
        svc = _service()
        svc.ping()
        return {
            "ok": True,
            "host": settings.ldap.host,
            "port": settings.ldap.port,
            "use_ssl": settings.ldap.use_ssl,
            "start_tls": settings.ldap.start_tls,
            "base_dn": settings.ldap.base_dn,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/groups", response_model=List[LdapGroup])
def list_groups():
    try:
        return _service().list_groups()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users", response_model=List[LdapUser])
def list_users():
    try:
        return _service().list_users()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tree", response_model=List[GroupTreeNode])
def group_tree(root_group: Optional[str] = Query(default=None, description="optional root group cn")):
    try:
        return _service().build_group_tree(root_group_cn=root_group)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))