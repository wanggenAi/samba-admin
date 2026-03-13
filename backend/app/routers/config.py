from fastapi import APIRouter, Depends

from ..schemas.samba import ConfigModel
from .authz import require_permission
from ..services.samba_service import validate_config, apply_config

router = APIRouter()


@router.post("/validate")
def validate(payload: ConfigModel, _: dict = Depends(require_permission("config.view"))):
    return validate_config(payload)


@router.post("/apply")
def apply(payload: ConfigModel, _: dict = Depends(require_permission("config.view"))):
    return apply_config(payload)
