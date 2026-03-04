from fastapi import APIRouter

from ..services.samba_service import list_versions, rollback_version

router = APIRouter()


@router.get("/")
def versions():
    return list_versions()


@router.post("/{vid}/rollback")
def rollback(vid: str):
    return rollback_version(vid)