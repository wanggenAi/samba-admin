from __future__ import annotations

from fastapi import HTTPException
from ldap3.core.exceptions import LDAPException

from ...schemas.users import UserDeleteResponse
from .. import get_ldap_service


def delete_user_by_username(username: str) -> UserDeleteResponse:
    uname = username.strip()
    if not uname:
        raise HTTPException(status_code=400, detail="username cannot be empty")
    if uname.lower() == "krbtgt":
        raise HTTPException(status_code=403, detail="cannot delete protected account: krbtgt")

    svc = get_ldap_service()
    with svc.connection() as conn:
        user_dn = svc.find_user_dn(conn, uname)
        if not user_dn:
            raise HTTPException(status_code=404, detail=f"user not found: {uname}")

        try:
            svc.delete_user(conn, user_dn)
        except LDAPException as e:
            raise HTTPException(status_code=400, detail=f"delete failed for '{uname}': {e}")
        return UserDeleteResponse(username=uname, deleted=True, dn=user_dn)
