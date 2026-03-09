from __future__ import annotations

from fastapi import HTTPException

from ..core.settings import settings
from .ldap_service import LdapService


def get_ldap_service() -> LdapService:
    cfg = settings.ldap
    if not cfg.bind_password:
        raise HTTPException(status_code=400, detail="LDAP_BIND_PASSWORD is empty (set env).")
    return LdapService(cfg)


__all__ = ["LdapService", "get_ldap_service"]
