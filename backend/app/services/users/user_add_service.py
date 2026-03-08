from __future__ import annotations

import subprocess
import ssl
from dataclasses import dataclass

import ldap3
from fastapi import HTTPException

from ...core.settings import settings
from ...schemas.users import UserAddRequest, UserAddResponse


@dataclass
class CmdResult:
    returncode: int
    output: str


def _run(cmd: list[str]) -> CmdResult:
    p = subprocess.run(cmd, capture_output=True, text=True)
    output = (p.stdout or "") + (p.stderr or "")
    return CmdResult(returncode=p.returncode, output=output)


def _require_bind_password() -> None:
    if not settings.ldap.bind_password:
        raise HTTPException(status_code=400, detail="LDAP_BIND_PASSWORD is empty (set env).")


def _user_exists(username: str) -> bool:
    p = _run(["samba-tool", "user", "show", username])
    return p.returncode == 0


def _ensure_group_exists(group_cn: str) -> None:
    p = _run(["samba-tool", "group", "show", group_cn])
    if p.returncode != 0:
        raise HTTPException(status_code=400, detail=f"group not found: {group_cn}")


def _create_or_overwrite_user(payload: UserAddRequest) -> tuple[bool, bool]:
    exists = _user_exists(payload.username)
    if not exists:
        p = _run(["samba-tool", "user", "create", payload.username, payload.password])
        if p.returncode != 0:
            raise HTTPException(status_code=500, detail={"stage": "create_user", "output": p.output})
        return True, False

    p = _run([
        "samba-tool",
        "user",
        "setpassword",
        payload.username,
        f"--newpassword={payload.password}",
    ])
    if p.returncode != 0:
        raise HTTPException(status_code=500, detail={"stage": "set_password", "output": p.output})
    return False, True


def _ldap_connect() -> ldap3.Connection:
    _require_bind_password()

    tls = None
    if settings.ldap.use_ssl or settings.ldap.start_tls:
        tls = ldap3.Tls(validate=ssl.CERT_NONE if settings.ldap.tls_skip_verify else ssl.CERT_REQUIRED)

    server = ldap3.Server(
        settings.ldap.host,
        port=settings.ldap.port,
        use_ssl=settings.ldap.use_ssl,
        tls=tls,
        get_info=ldap3.NONE,
    )

    conn = ldap3.Connection(
        server,
        user=settings.ldap.bind_user,
        password=settings.ldap.bind_password,
        auto_bind=False,
    )
    conn.open()

    if settings.ldap.start_tls and not settings.ldap.use_ssl:
        if not conn.start_tls():
            raise HTTPException(status_code=500, detail=f"start_tls failed: {conn.result}")

    if not conn.bind():
        raise HTTPException(status_code=500, detail=f"ldap bind failed: {conn.result}")

    return conn


def _find_user_dn(conn: ldap3.Connection, username: str) -> str:
    flt = f"(sAMAccountName={ldap3.utils.conv.escape_filter_chars(username)})"
    ok = conn.search(
        search_base=settings.ldap.base_dn,
        search_filter=flt,
        attributes=["distinguishedName"],
    )
    if not ok or not conn.entries:
        raise HTTPException(status_code=500, detail=f"cannot find DN for user: {username}")
    return str(getattr(conn.entries[0], "distinguishedName"))


def _update_user_attributes(payload: UserAddRequest) -> list[str]:
    conn = _ldap_connect()
    updated: list[str] = []
    try:
        user_dn = _find_user_dn(conn, payload.username)

        changes: dict[str, list[tuple[int, list[str]]]] = {
            "displayName": [(ldap3.MODIFY_REPLACE, [payload.russian_name])],
            "givenName": [(ldap3.MODIFY_REPLACE, [payload.pinyin_name])],
            "employeeID": [(ldap3.MODIFY_REPLACE, [payload.student_id])],
        }

        if payload.paid_flag == "$":
            changes["employeeType"] = [(ldap3.MODIFY_REPLACE, ["$"])]
        elif payload.paid_flag is None:
            changes["employeeType"] = [(ldap3.MODIFY_DELETE, [])]

        ok = conn.modify(user_dn, changes)
        if not ok:
            raise HTTPException(
                status_code=500,
                detail={"stage": "update_attributes", "output": str(conn.result)},
            )

        updated.extend(changes.keys())
        return updated
    finally:
        conn.unbind()


def _ensure_group_memberships(username: str, groups: list[str]) -> list[str]:
    added: list[str] = []
    for g in groups:
        _ensure_group_exists(g)
        p = _run(["samba-tool", "group", "addmembers", g, username])
        if p.returncode != 0 and "already a member" not in p.output.lower():
            raise HTTPException(
                status_code=500,
                detail={"stage": "add_group_membership", "group": g, "output": p.output},
            )
        added.append(g)
    return added


def add_or_overwrite_user(payload: UserAddRequest) -> UserAddResponse:
    created, password_updated = _create_or_overwrite_user(payload)
    updated_attributes = _update_user_attributes(payload)
    groups_added = _ensure_group_memberships(payload.username, payload.groups)

    return UserAddResponse(
        username=payload.username,
        created=created,
        password_updated=password_updated,
        updated_attributes=updated_attributes,
        groups_added=groups_added,
    )
