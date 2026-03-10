from __future__ import annotations

import re
import unicodedata

import ldap3
from fastapi import HTTPException
from ldap3.core.exceptions import LDAPException

from ...schemas.users import UserAddRequest, UserAddResponse
from .. import get_ldap_service
from ..ldap_service import LdapService

MAX_USERNAME_LEN = 64


def _username_from_dn(dn: str) -> str:
    first = str(dn or "").split(",", 1)[0].strip()
    if first.upper().startswith("CN="):
        return first[3:].strip()
    return ""


def _parent_dn_from_dn(dn: str) -> str:
    parts = str(dn or "").split(",", 1)
    if len(parts) != 2 or not parts[1].strip():
        raise HTTPException(status_code=400, detail="invalid user DN")
    return parts[1].strip()


def _normalize_username_seed(value: str) -> str:
    raw = unicodedata.normalize("NFKD", value or "")
    ascii_value = raw.encode("ascii", "ignore").decode("ascii")
    token = re.sub(r"[^a-zA-Z0-9._-]+", "", ascii_value).lower()
    return token.strip("._-")


def _build_username_seeds(first_name: str, last_name: str, student_id: str) -> list[str]:
    first = _normalize_username_seed(first_name)
    last = _normalize_username_seed(last_name)
    sid = _normalize_username_seed(student_id)

    raw_candidates = [
        f"{first}.{last}" if first and last else "",
        f"{first}{last}",
        last,
        first,
        sid,
        "user",
    ]
    out: list[str] = []
    seen: set[str] = set()
    for candidate in raw_candidates:
        c = candidate.strip("._-")[:MAX_USERNAME_LEN]
        if not c or c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def _find_available_username(conn: ldap3.Connection, svc: LdapService, base: str) -> str:
    seed = (base or "").strip()[:MAX_USERNAME_LEN]
    if not seed:
        raise HTTPException(status_code=422, detail="cannot generate username")

    if not svc.find_user_dn(conn, seed):
        return seed

    for i in range(1, 10000):
        suffix = str(i)
        room = max(1, MAX_USERNAME_LEN - len(suffix))
        candidate = f"{seed[:room]}{suffix}"
        if not svc.find_user_dn(conn, candidate):
            return candidate

    raise HTTPException(status_code=409, detail="cannot allocate available username")


def _resolve_create_username(conn: ldap3.Connection, svc: LdapService, payload: UserAddRequest) -> str:
    requested = (payload.username or "").strip()
    if requested:
        return _find_available_username(conn, svc, requested)

    for seed in _build_username_seeds(payload.first_name, payload.last_name, payload.student_id):
        username = _find_available_username(conn, svc, seed)
        if username:
            return username

    raise HTTPException(status_code=422, detail="cannot generate username from provided names")


def _raise_move_user_http_error(username: str, ou_path: list[str], err: LDAPException) -> None:
    msg = str(err)
    if "target DN already exists" in msg:
        raise HTTPException(
            status_code=409,
            detail=(
                f"cannot move user '{username}' to OU path "
                f"'{'/'.join(ou_path)}': target CN already exists"
            ),
        )
    if "insufficient access rights" in msg:
        raise HTTPException(
            status_code=403,
            detail=f"insufficient LDAP rights to move user '{username}'",
        )
    raise HTTPException(
        status_code=400,
        detail=f"failed to move user '{username}' to requested OU path",
    )


def _add_user_groups(
    svc: LdapService,
    conn: ldap3.Connection,
    user_dn: str,
    groups: list[str],
) -> list[str]:
    groups_added: list[str] = []
    for group_cn in groups:
        group_dn = svc.find_group_dn(conn, group_cn)
        if not group_dn:
            raise HTTPException(status_code=400, detail=f"group not found: {group_cn}")
        svc.add_user_to_group(conn, user_dn, group_dn)
        groups_added.append(group_cn)
    return groups_added


def add_or_overwrite_user(payload: UserAddRequest) -> UserAddResponse:
    svc = get_ldap_service()
    with svc.connection() as conn:
        password = (payload.password or "").strip()
        source_username = (payload.source_username or "").strip()
        requested_username = (payload.username or "").strip()
        if source_username:
            user_dn = svc.find_user_dn(conn, source_username)
            if not user_dn:
                raise HTTPException(status_code=404, detail=f"user not found: {source_username}")
        else:
            user_dn = svc.find_user_dn(conn, requested_username) if requested_username else None

        current_username = source_username if source_username else requested_username
        active_username = requested_username
        created = False
        password_updated = False
        target_parent_dn = svc.ensure_ou_path(conn, payload.ou_path) if payload.ou_path else None
        moved = False
        renamed = False
        renamed_attributes: list[str] = []

        if not user_dn:
            if not password:
                raise HTTPException(status_code=422, detail="password is required when creating a new user")
            active_username = _resolve_create_username(conn, svc, payload)
            user_dn = svc.create_user(
                conn,
                active_username,
                password,
                parent_dn=target_parent_dn,
                first_name=payload.first_name,
                last_name=payload.last_name,
                display_name=payload.display_name,
            )
            created = True
        else:
            if not current_username:
                current_username = _username_from_dn(user_dn)
            if not current_username:
                raise HTTPException(status_code=400, detail="cannot resolve username for existing user")

            if not active_username:
                active_username = current_username

            if active_username.lower() != current_username.lower():
                conflict_dn = svc.find_user_dn(conn, active_username)
                if conflict_dn and conflict_dn.lower() != user_dn.lower():
                    raise HTTPException(status_code=409, detail=f"user already exists: {active_username}")
                renamed = True

            if target_parent_dn or renamed:
                destination_parent_dn = target_parent_dn or _parent_dn_from_dn(user_dn)
                try:
                    next_dn = svc.move_user_to_parent(
                        conn,
                        user_dn=user_dn,
                        username=active_username,
                        parent_dn=destination_parent_dn,
                    )
                except LDAPException as e:
                    _raise_move_user_http_error(active_username, payload.ou_path, e)

                moved = next_dn.lower() != user_dn.lower()
                user_dn = next_dn

            if renamed:
                renamed_attributes = svc.update_user_login_identifiers(conn, user_dn, active_username)

            if password:
                svc.set_user_password(conn, user_dn, password)
                password_updated = True

        profile_updated_attributes = svc.update_user_profile(
            conn=conn,
            user_dn=user_dn,
            student_id=payload.student_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            display_name=payload.display_name,
            paid_flag=payload.paid_flag,
        )
        updated_attributes = renamed_attributes + profile_updated_attributes

        groups_added = _add_user_groups(svc, conn, user_dn, payload.groups)

        return UserAddResponse(
            username=active_username,
            created=created,
            password_updated=password_updated,
            moved=moved,
            moved_to_dn=(user_dn if moved else None),
            updated_attributes=updated_attributes,
            groups_added=groups_added,
        )
