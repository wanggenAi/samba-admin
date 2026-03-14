from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.routers.authz import get_current_user, require_any_permission, require_permission


class AuthzTests(unittest.TestCase):
    def test_get_current_user_missing_token(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_get_current_user_invalid_scheme(self) -> None:
        cred = HTTPAuthorizationCredentials(scheme="Basic", credentials="x")
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(cred)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_get_current_user_subject_missing(self) -> None:
        cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials="x")
        with patch("app.routers.authz.auth_service.decode_token", return_value={}):
            with self.assertRaises(HTTPException) as ctx:
                get_current_user(cred)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_get_current_user_success(self) -> None:
        cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials="x")
        with patch("app.routers.authz.auth_service.decode_token", return_value={"sub": "admin"}):
            with patch("app.routers.authz.auth_service.get_user", return_value={"username": "admin"}):
                user = get_current_user(cred)
        self.assertEqual(user["username"], "admin")

    def test_require_permission_and_any_permission(self) -> None:
        dep = require_permission("users.view")
        with patch("app.routers.authz.auth_service.has_permission", return_value=False):
            with self.assertRaises(HTTPException) as ctx:
                dep({"username": "u"})
        self.assertEqual(ctx.exception.status_code, 403)

        dep_any = require_any_permission("users.create", "users.edit")
        with patch("app.routers.authz.auth_service.has_permission", return_value=True):
            user = dep_any({"username": "u"})
        self.assertEqual(user["username"], "u")

        with patch("app.routers.authz.auth_service.has_permission", return_value=False):
            with self.assertRaises(HTTPException) as ctx_any:
                dep_any({"username": "u"})
        self.assertEqual(ctx_any.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
