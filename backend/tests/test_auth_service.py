from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app.core.settings import settings
from app.services.auth_service import AuthService


class AuthServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_file = Path(self._tmp.name) / "rbac.json"
        self.svc = AuthService(self.data_file)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_initialization_creates_default_admin_and_authenticates(self) -> None:
        user = self.svc.authenticate("admin", "admin123")
        self.assertEqual(user["username"], "admin")
        self.assertIn("*", user["permissions"])

    def test_validate_username_rejects_over_64_chars(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            self.svc.authenticate("a" * 65, "x")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("too long", str(ctx.exception.detail))

    def test_create_permission_rejects_invalid_format(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            self.svc.create_permission("Bad.Permission", "x")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("invalid permission", str(ctx.exception.detail))

    def test_create_role_requires_known_non_empty_permissions(self) -> None:
        with self.assertRaises(HTTPException) as ctx_empty:
            self.svc.create_role("r1", "", [])
        self.assertEqual(ctx_empty.exception.status_code, 400)

        with self.assertRaises(HTTPException) as ctx_unknown:
            self.svc.create_role("r2", "", ["custom.unknown"])
        self.assertEqual(ctx_unknown.exception.status_code, 400)
        self.assertIn("unknown permission", str(ctx_unknown.exception.detail))

    def test_create_and_update_user_boundary_paths(self) -> None:
        self.svc.create_permission("custom.read", "custom")
        role = self.svc.create_role("auditor", "audit", ["users.view", "custom.read"])
        self.assertEqual(role["name"], "auditor")

        created = self.svc.create_user("alice", "A1!pass", ["auditor"], disabled=False)
        self.assertEqual(created["username"], "alice")
        self.assertIn("custom.read", created["permissions"])

        with self.assertRaises(HTTPException) as ctx_pw:
            self.svc.update_user("alice", password="")
        self.assertEqual(ctx_pw.exception.status_code, 400)
        self.assertIn("cannot be empty", str(ctx_pw.exception.detail))

        updated = self.svc.update_user("alice", disabled=True)
        self.assertTrue(updated["disabled"])

        with self.assertRaises(HTTPException) as ctx_disabled:
            self.svc.authenticate("alice", "A1!pass")
        self.assertEqual(ctx_disabled.exception.status_code, 403)

    def test_token_round_trip_and_expired_token(self) -> None:
        old_secret = settings.jwt_secret
        try:
            settings.jwt_secret = "unit-test-secret"
            user = self.svc.authenticate("admin", "admin123")
            token = self.svc.issue_token(user)
            payload = self.svc.decode_token(token)
            self.assertEqual(payload["sub"], "admin")
        finally:
            settings.jwt_secret = old_secret


if __name__ == "__main__":
    unittest.main()
