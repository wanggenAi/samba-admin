from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.users import UserAddRequest, UserAddResponse
from ..services.users import add_or_overwrite_user

router = APIRouter()


@router.post("", response_model=UserAddResponse)
def add_user(payload: UserAddRequest):
    try:
        return add_or_overwrite_user(payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
