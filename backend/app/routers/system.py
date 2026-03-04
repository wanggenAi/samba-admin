from fastapi import APIRouter
from ..services.samba_service import get_service_status

router = APIRouter()


@router.get("/status")
def status():
    return get_service_status()