from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..services.auth_service import auth_service

bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="Input JWT token as: Bearer <token>",
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="missing bearer token")
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="invalid auth scheme")
    token_payload = auth_service.decode_token(credentials.credentials)
    sub = str(token_payload.get("sub", "")).strip()
    if not sub:
        raise HTTPException(status_code=401, detail="token subject missing")
    return auth_service.get_user(sub)


def require_permission(permission: str) -> Callable[[dict], dict]:
    def _dep(user: dict = Depends(get_current_user)) -> dict:
        if not auth_service.has_permission(user, permission):
            raise HTTPException(status_code=403, detail=f"permission denied: {permission}")
        return user

    return _dep


def require_any_permission(*permissions: str) -> Callable[[dict], dict]:
    normalized = [p for p in permissions if p]

    def _dep(user: dict = Depends(get_current_user)) -> dict:
        for p in normalized:
            if auth_service.has_permission(user, p):
                return user
        raise HTTPException(status_code=403, detail=f"permission denied: any of {normalized}")

    return _dep
