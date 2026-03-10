from __future__ import annotations

import ldap3
from fastapi import HTTPException
from ldap3.core.exceptions import LDAPException

from ...schemas.users import UserAddRequest, UserAddResponse
from .. import get_ldap_service
from ..ldap_service import LdapService


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
        user_dn = svc.find_user_dn(conn, payload.username)
        created = False
        password_updated = False
        target_parent_dn = svc.ensure_ou_path(conn, payload.ou_path) if payload.ou_path else None
        moved = False

        if not user_dn:
            if not password:
                raise HTTPException(status_code=422, detail="password is required when creating a new user")
            user_dn = svc.create_user(conn, payload.username, password, parent_dn=target_parent_dn)
            created = True
        else:
            if target_parent_dn:
                try:
                    next_dn = svc.move_user_to_parent(
                        conn,
                        user_dn=user_dn,
                        username=payload.username,
                        parent_dn=target_parent_dn,
                    )
                except LDAPException as e:
                    _raise_move_user_http_error(payload.username, payload.ou_path, e)

                moved = next_dn.lower() != user_dn.lower()
                user_dn = next_dn
            if password:
                svc.set_user_password(conn, user_dn, password)
                password_updated = True

        updated_attributes = svc.update_user_profile(
            conn=conn,
            user_dn=user_dn,
            student_id=payload.student_id,
            russian_name=payload.russian_name,
            pinyin_name=payload.pinyin_name,
            paid_flag=payload.paid_flag,
        )

        groups_added = _add_user_groups(svc, conn, user_dn, payload.groups)

        return UserAddResponse(
            username=payload.username,
            created=created,
            password_updated=password_updated,
            moved=moved,
            moved_to_dn=(user_dn if moved else None),
            updated_attributes=updated_attributes,
            groups_added=groups_added,
        )
