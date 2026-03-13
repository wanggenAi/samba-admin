from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def _trim_username(cls, value: str) -> str:
        v = value.strip()
        if not v:
            raise ValueError("username is required")
        return v


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class RoleUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=256)
    permissions: list[str] = Field(default_factory=list)


class RolePatchRequest(BaseModel):
    description: str | None = Field(default=None, max_length=256)
    permissions: list[str] | None = None


class PermissionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=256)


class PermissionPatchRequest(BaseModel):
    description: str = Field(default="", max_length=256)


class AdminUserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    roles: list[str] = Field(default_factory=list)
    disabled: bool = False


class AdminUserPatchRequest(BaseModel):
    password: str | None = Field(default=None, max_length=256)
    roles: list[str] | None = None
    disabled: bool | None = None
