from __future__ import annotations

from datetime import datetime, timezone
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from ..routers.authz import require_any_permission, require_permission
from ..routers import ldap_guard
from ..schemas.users import UserAddRequest, UserAddResponse, UserDeleteResponse, UserImportResponse
from ..services.users import (
    add_or_overwrite_user,
    delete_user_by_username,
    export_users_csv,
    import_users_from_legacy_txt,
)

router = APIRouter()
MAX_IMPORT_FILE_BYTES = 2 * 1024 * 1024
MAX_IMPORT_TOTAL_BYTES = 10 * 1024 * 1024


async def _read_upload_with_limit(upload: UploadFile, max_size: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"file too large: {upload.filename or 'upload.txt'} (limit {max_size} bytes)",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", response_model=UserAddResponse)
def add_user(payload: UserAddRequest, _: dict = Depends(require_any_permission("users.create", "users.edit"))):
    return ldap_guard(lambda: add_or_overwrite_user(payload))


@router.delete("/{username}", response_model=UserDeleteResponse)
def delete_user(username: str, _: dict = Depends(require_permission("users.delete"))):
    return ldap_guard(lambda: delete_user_by_username(username))


@router.post("/import", response_model=UserImportResponse)
async def import_users(
    files: list[UploadFile] = File(..., description="one or more legacy txt files"),
    default_group_cn: str | None = Form(default="Students"),
    password_length: int = Form(default=12),
    _: dict = Depends(require_permission("users.import")),
):
    loaded_files: list[tuple[str, bytes]] = []
    total_size = 0
    for f in files:
        try:
            raw = await _read_upload_with_limit(f, MAX_IMPORT_FILE_BYTES)
        finally:
            await f.close()
        total_size += len(raw)
        if total_size > MAX_IMPORT_TOTAL_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"total upload size too large (limit {MAX_IMPORT_TOTAL_BYTES} bytes)",
            )
        loaded_files.append((f.filename or "upload.txt", raw))

    return ldap_guard(
        lambda: import_users_from_legacy_txt(
            loaded_files,
            default_group_cn=default_group_cn,
            password_length=password_length,
        )
    )


@router.get("/export")
def export_users(
    keyword: str | None = Query(default=None, description="keyword filter from user list search"),
    ou_dn: list[str] = Query(default_factory=list, description="OU DN filters"),
    group_cn: list[str] | None = Query(default=None, description="group CN filters"),
    _: dict = Depends(require_permission("users.export")),
):
    data = ldap_guard(lambda: export_users_csv(keyword=keyword, ou_dns=ou_dn, group_cns=group_cn or []))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"users-export-{stamp}.csv"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
