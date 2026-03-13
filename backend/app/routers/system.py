from fastapi import APIRouter, Depends

from .authz import require_permission
from ..services.samba_service import get_service_status

router = APIRouter()


@router.get("/status")
def status(_: dict = Depends(require_permission("dashboard.view"))):
    return get_service_status()
