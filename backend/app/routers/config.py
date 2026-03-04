from fastapi import APIRouter

from ..models.schema import ConfigModel
from ..services.samba_service import validate_config, apply_config

router = APIRouter()


@router.post("/validate")
def validate(payload: ConfigModel):
    return validate_config(payload)


@router.post("/apply")
def apply(payload: ConfigModel):
    return apply_config(payload)