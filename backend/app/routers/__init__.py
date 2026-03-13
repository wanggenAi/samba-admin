from __future__ import annotations

import logging
from typing import Callable, TypeVar

from fastapi import HTTPException
from ldap3.core.exceptions import LDAPException

T = TypeVar("T")
logger = logging.getLogger(__name__)


def ldap_guard(fn: Callable[[], T]) -> T:
    try:
        return fn()
    except HTTPException:
        raise
    except LDAPException as e:
        message = str(e)
        lower = message.lower()
        logger.exception("LDAP operation failed: %s", message)
        if (
            "connection refused" in lower
            or "socket connection error" in lower
            or "timed out" in lower
            or "network is unreachable" in lower
        ):
            raise HTTPException(
                status_code=503,
                detail=f"LDAP server unavailable: {message}",
            )
        raise HTTPException(status_code=500, detail=message)
    except Exception as e:
        logger.exception("Unhandled backend error: %s", e)
        raise HTTPException(status_code=500, detail="internal server error")
