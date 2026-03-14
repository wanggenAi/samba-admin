from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app.services.auth_service import AuthService, _hash_password, _verify_password


class AuthServiceInternalTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "rbac.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _svc(self) -> AuthService:
        return AuthService(self.path)

    def test_hash_and_verify_password(self) -> None:
        encoded = _hash_password("Secret@123")
        self.assertTrue(_verify_password("Secret@123", encoded))
        self.assertFalse(_verify_password("wrong", encoded))
        self.assertFalse(_verify_password("x", "invalid-format"))
        self.assertFalse(_verify_password("x", "md5$1$a$b"))

    def test_ensure_initialized_repairs_missing_sections(self) -> None:
        self.path.write_text(json.dumps({"users": "bad"}), encoding="utf-8")
        svc = self._svc()
        data = svc._read()
        self.assertIsInstance(data.get("users"), list)
        self.assertIsInstance(data.get("roles"), list)
        self.assertIsInstance(data.get("permissions"), list)

    def test_read_raises_on_invalid_json_and_non_dict(self) -> None:
        self.path.write_text("not-json", encoding="utf-8")
        with self.assertRaises(HTTPException) as ctx_json:
            self._svc()
        self.assertEqual(ctx_json.exception.status_code, 500)

        self.path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with self.assertRaises(HTTPException) as ctx_type:
            self._svc()
        self.assertEqual(ctx_type.exception.status_code, 500)

    def test_internal_permission_and_role_validation_paths(self) -> None:
        svc = self._svc()
        data = svc._read()

        perms = svc._normalize_permissions(["users.view", "users.view", "*"], data)
        self.assertEqual(perms, ["users.view", "*"])

        with self.assertRaises(HTTPException):
            svc._normalize_permissions(["unknown.perm"], data)

        role_map = svc._resolve_role_map(data)
        valid = svc._validate_roles_exist(["viewer", "viewer"], role_map)
        self.assertEqual(valid, ["viewer"])

        with self.assertRaises(HTTPException):
            svc._validate_roles_exist([], role_map)

        with self.assertRaises(HTTPException):
            svc._validate_roles_exist(["missing"], role_map)

    def test_resolve_role_map_invalid_format(self) -> None:
        svc = self._svc()
        with self.assertRaises(HTTPException) as ctx:
            svc._resolve_role_map({"roles": "bad"})
        self.assertEqual(ctx.exception.status_code, 500)

    def test_not_found_paths(self) -> None:
        svc = self._svc()
        with self.assertRaises(HTTPException) as ctx_p:
            svc.delete_permission("custom.none")
        self.assertEqual(ctx_p.exception.status_code, 404)

        with self.assertRaises(HTTPException) as ctx_r:
            svc.update_role("missing", description="x", permissions=None)
        self.assertEqual(ctx_r.exception.status_code, 404)

        with self.assertRaises(HTTPException) as ctx_u:
            svc.delete_user("nobody")
        self.assertEqual(ctx_u.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
