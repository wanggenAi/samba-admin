from fastapi import APIRouter, Depends

from .authz import require_permission
from ..services.samba_service import list_versions, rollback_version

router = APIRouter()


@router.get("/")
def versions(_: dict = Depends(require_permission("versions.view"))):
    return list_versions()


@router.post("/{vid}/rollback")
def rollback(vid: str, _: dict = Depends(require_permission("versions.view"))):
    return rollback_version(vid)
