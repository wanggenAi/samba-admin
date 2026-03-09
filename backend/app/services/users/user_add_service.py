from __future__ import annotations

from fastapi import HTTPException

from ...schemas.users import UserAddRequest, UserAddResponse
from .. import get_ldap_service


def add_or_overwrite_user(payload: UserAddRequest) -> UserAddResponse:
    svc = get_ldap_service()
    with svc.connection() as conn:
        user_dn = svc.find_user_dn(conn, payload.username)
        created = False
        password_updated = False

        if not user_dn:
            user_dn = svc.create_user(conn, payload.username, payload.password)
            created = True
        else:
            svc.set_user_password(conn, user_dn, payload.password)
            password_updated = True

        updated_attributes = svc.update_user_profile(
            conn=conn,
            user_dn=user_dn,
            student_id=payload.student_id,
            russian_name=payload.russian_name,
            pinyin_name=payload.pinyin_name,
            paid_flag=payload.paid_flag,
        )

        groups_added: list[str] = []
        for group_cn in payload.groups:
            group_dn = svc.find_group_dn(conn, group_cn)
            if not group_dn:
                raise HTTPException(status_code=400, detail=f"group not found: {group_cn}")
            svc.add_user_to_group(conn, user_dn, group_dn)
            groups_added.append(group_cn)

        return UserAddResponse(
            username=payload.username,
            created=created,
            password_updated=password_updated,
            updated_attributes=updated_attributes,
            groups_added=groups_added,
        )
