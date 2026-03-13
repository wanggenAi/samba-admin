from __future__ import annotations

from fastapi import HTTPException

from ..core import settings
from ..schemas.samba import ConfigModel


def _samba_disabled() -> HTTPException:
    return HTTPException(
        status_code=501,
        detail=(
            "samba command features are disabled in LDAP-only mode; "
            "this backend instance only supports LDAP APIs"
        ),
    )


def get_service_status() -> dict:
    # LDAP-only development mode: do not call systemctl/samba-tool.
    return {
        "service": settings.samba.service_name,
        "active": False,
        "raw": "disabled (ldap-only mode)",
        "mode": "ldap-only",
    }


def validate_config(payload: ConfigModel) -> dict:
    _ = payload
    raise _samba_disabled()


def apply_config(payload: ConfigModel) -> dict:
    _ = payload
    raise _samba_disabled()


def list_versions() -> list[dict]:
    return []


def rollback_version(vid: str) -> dict:
    _ = vid
    raise _samba_disabled()
