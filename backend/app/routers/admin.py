from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..routers.authz import get_current_user, require_permission
from ..schemas.auth import (
    AdminUserCreateRequest,
    AdminUserPatchRequest,
    PermissionCreateRequest,
    PermissionPatchRequest,
    RolePatchRequest,
    RoleUpsertRequest,
)
from ..services.auth_service import auth_service

router = APIRouter()


@router.get("/permissions")
def list_permissions(_: dict = Depends(require_permission("system.manage"))):
    return auth_service.list_permissions()


@router.post("/permissions")
def create_permission(payload: PermissionCreateRequest, _: dict = Depends(require_permission("system.manage"))):
    return auth_service.create_permission(
        name=payload.name,
        description=payload.description,
    )


@router.patch("/permissions/{name}")
def update_permission(
    name: str,
    payload: PermissionPatchRequest,
    _: dict = Depends(require_permission("system.manage")),
):
    return auth_service.update_permission(name=name, description=payload.description)


@router.delete("/permissions/{name}")
def delete_permission(name: str, _: dict = Depends(require_permission("system.manage"))):
    return auth_service.delete_permission(name)


@router.get("/roles")
def list_roles(_: dict = Depends(require_permission("system.manage"))):
    return auth_service.list_roles()


@router.post("/roles")
def create_role(payload: RoleUpsertRequest, _: dict = Depends(require_permission("system.manage"))):
    return auth_service.create_role(
        name=payload.name,
        description=payload.description,
        permissions=payload.permissions,
    )


@router.patch("/roles/{name}")
def update_role(name: str, payload: RolePatchRequest, _: dict = Depends(require_permission("system.manage"))):
    return auth_service.update_role(
        role_name=name,
        description=payload.description,
        permissions=payload.permissions,
    )


@router.delete("/roles/{name}")
def delete_role(name: str, _: dict = Depends(require_permission("system.manage"))):
    return auth_service.delete_role(name)


@router.get("/users")
def list_users(_: dict = Depends(require_permission("system.manage"))):
    return auth_service.list_users()


@router.post("/users")
def create_user(payload: AdminUserCreateRequest, _: dict = Depends(require_permission("system.manage"))):
    return auth_service.create_user(
        username=payload.username,
        password=payload.password,
        roles=payload.roles,
        disabled=payload.disabled,
    )


@router.patch("/users/{username}")
def patch_user(
    username: str,
    payload: AdminUserPatchRequest,
    _: dict = Depends(require_permission("system.manage")),
):
    return auth_service.update_user(
        username=username,
        password=payload.password,
        roles=payload.roles,
        disabled=payload.disabled,
    )


@router.delete("/users/{username}")
def delete_user(
    username: str,
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(require_permission("system.manage")),
):
    if username == current_user["username"]:
        raise HTTPException(status_code=400, detail="cannot delete current user")
    return auth_service.delete_user(username)
