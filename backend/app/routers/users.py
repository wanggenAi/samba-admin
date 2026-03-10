from __future__ import annotations

from datetime import datetime, timezone
import io

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from ..routers import ldap_guard
from ..schemas.users import UserAddRequest, UserAddResponse, UserDeleteResponse, UserImportResponse
from ..services.users import (
    add_or_overwrite_user,
    delete_user_by_username,
    export_users_csv,
    import_users_from_legacy_txt,
)

router = APIRouter()


@router.post("", response_model=UserAddResponse)
def add_user(payload: UserAddRequest):
    return ldap_guard(lambda: add_or_overwrite_user(payload))


@router.delete("/{username}", response_model=UserDeleteResponse)
def delete_user(username: str):
    return ldap_guard(lambda: delete_user_by_username(username))


@router.post("/import", response_model=UserImportResponse)
async def import_users(
    files: list[UploadFile] = File(..., description="one or more legacy txt files"),
    default_group_cn: str | None = Form(default="Students"),
    password_length: int = Form(default=12),
):
    loaded_files: list[tuple[str, bytes]] = []
    for f in files:
        raw = await f.read()
        loaded_files.append((f.filename or "upload.txt", raw))

    return ldap_guard(
        lambda: import_users_from_legacy_txt(
            loaded_files,
            default_group_cn=default_group_cn,
            password_length=password_length,
        )
    )


@router.get("/export")
def export_users():
    data = ldap_guard(export_users_csv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"users-export-{stamp}.csv"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
