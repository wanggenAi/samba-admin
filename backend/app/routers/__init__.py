from __future__ import annotations

from typing import Callable, TypeVar

from fastapi import HTTPException

T = TypeVar("T")


def ldap_guard(fn: Callable[[], T]) -> T:
    try:
        return fn()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
