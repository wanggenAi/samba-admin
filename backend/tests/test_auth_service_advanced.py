from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app.services.auth_service import AuthService


class AuthServiceAdvancedTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.svc = AuthService(Path(self._tmp.name) / "rbac.json")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_permission_crud_branches(self) -> None:
        created = self.svc.create_permission("custom.read", "Custom read")
        self.assertEqual(created["name"], "custom.read")

        with self.assertRaises(HTTPException) as ctx_dup:
            self.svc.create_permission("custom.read", "x")
        self.assertEqual(ctx_dup.exception.status_code, 409)

        updated = self.svc.update_permission("custom.read", "Updated")
        self.assertEqual(updated["description"], "Updated")

        with self.assertRaises(HTTPException) as ctx_builtin:
            self.svc.update_permission("users.view", "x")
        self.assertEqual(ctx_builtin.exception.status_code, 400)

        deleted = self.svc.delete_permission("custom.read")
        self.assertTrue(deleted["ok"])

    def test_delete_permission_blocked_when_assigned(self) -> None:
        self.svc.create_permission("custom.write", "Custom write")
        self.svc.create_role("writer", "role", ["custom.write"])
        with self.assertRaises(HTTPException) as ctx:
            self.svc.delete_permission("custom.write")
        self.assertEqual(ctx.exception.status_code, 409)

    def test_role_crud_branches(self) -> None:
        role = self.svc.create_role("auditor", "Audit", ["users.view"])
        self.assertEqual(role["name"], "auditor")

        with self.assertRaises(HTTPException) as ctx_dup:
            self.svc.create_role("auditor", "x", ["users.view"])
        self.assertEqual(ctx_dup.exception.status_code, 409)

        patched = self.svc.update_role("auditor", description="Audit2", permissions=["dashboard.view"])
        self.assertEqual(patched["description"], "Audit2")
        self.assertEqual(patched["permissions"], ["dashboard.view"])

        with self.assertRaises(HTTPException) as ctx_builtin:
            self.svc.update_role("super_admin", description="x", permissions=None)
        self.assertEqual(ctx_builtin.exception.status_code, 400)

        deleted = self.svc.delete_role("auditor")
        self.assertTrue(deleted["ok"])

        with self.assertRaises(HTTPException) as ctx_builtin_del:
            self.svc.delete_role("viewer")
        self.assertEqual(ctx_builtin_del.exception.status_code, 400)

    def test_delete_role_blocked_when_assigned(self) -> None:
        self.svc.create_role("auditor", "Audit", ["users.view"])
        self.svc.create_user("bob", "B0b!pass", ["auditor"], disabled=False)
        with self.assertRaises(HTTPException) as ctx:
            self.svc.delete_role("auditor")
        self.assertEqual(ctx.exception.status_code, 409)

    def test_user_crud_and_auth_branches(self) -> None:
        with self.assertRaises(HTTPException) as ctx_unknown_role:
            self.svc.create_user("alice", "A1!pass", ["missing-role"], disabled=False)
        self.assertEqual(ctx_unknown_role.exception.status_code, 400)

        self.svc.create_user("alice", "A1!pass", ["viewer"], disabled=False)
        with self.assertRaises(HTTPException) as ctx_dup:
            self.svc.create_user("ALICE", "A1!pass", ["viewer"], disabled=False)
        self.assertEqual(ctx_dup.exception.status_code, 409)

        with self.assertRaises(HTTPException) as ctx_bad_login:
            self.svc.authenticate("alice", "wrong")
        self.assertEqual(ctx_bad_login.exception.status_code, 401)

        updated = self.svc.update_user("alice", roles=["operator"], disabled=True)
        self.assertTrue(updated["disabled"])

        with self.assertRaises(HTTPException) as ctx_disabled:
            self.svc.get_user("alice")
        self.assertEqual(ctx_disabled.exception.status_code, 403)

        with self.assertRaises(HTTPException) as ctx_not_found:
            self.svc.update_user("nobody", disabled=True)
        self.assertEqual(ctx_not_found.exception.status_code, 404)

    def test_decode_token_invalid_and_permission_helper(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            self.svc.decode_token("not-a-jwt")
        self.assertEqual(ctx.exception.status_code, 401)

        self.assertTrue(self.svc.has_permission({"permissions": ["*"]}, "users.delete"))
        self.assertFalse(self.svc.has_permission({"permissions": ["users.view"]}, "users.delete"))


if __name__ == "__main__":
    unittest.main()
