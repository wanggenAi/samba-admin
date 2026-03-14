from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from ldap3.core.exceptions import LDAPException

from app.main import create_app
from app.services.auth_service import AuthService


class ApiIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.auth = AuthService(Path(self._tmp.name) / "rbac.json")

        self._patchers = [
            patch("app.routers.auth.auth_service", self.auth),
            patch("app.routers.admin.auth_service", self.auth),
            patch("app.routers.authz.auth_service", self.auth),
        ]
        for p in self._patchers:
            p.start()

        self.app = create_app()
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        for p in reversed(self._patchers):
            p.stop()
        self._tmp.cleanup()

    def _login(self, username: str, password: str) -> str:
        r = self.client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["access_token"]

    def test_login_and_me_flow(self) -> None:
        token = self._login("admin", "admin123")
        r = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["username"], "admin")

    def test_auth_me_requires_token(self) -> None:
        r = self.client.get("/api/auth/me")
        self.assertEqual(r.status_code, 401)
        self.assertIn("missing bearer token", r.text)

    def test_change_password_flow(self) -> None:
        token = self._login("admin", "admin123")
        r = self.client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "admin123", "new_password": "Adm1n@new"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        _ = self._login("admin", "Adm1n@new")

    def test_permission_denied_for_non_system_user(self) -> None:
        self.auth.create_user("viewer1", "Viewer@123", ["viewer"], disabled=False)
        token = self._login("viewer1", "Viewer@123")

        r = self.client.get("/api/admin/permissions", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("permission denied", r.text)

    def test_admin_crud_endpoints(self) -> None:
        token = self._login("admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}

        self.assertEqual(self.client.get("/api/admin/permissions", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/roles", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/users", headers=headers).status_code, 200)

        r = self.client.post(
            "/api/admin/permissions",
            headers=headers,
            json={"name": "custom.audit", "description": "audit"},
        )
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.patch(
            "/api/admin/permissions/custom.audit",
            headers=headers,
            json={"description": "audit2"},
        )
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post(
            "/api/admin/roles",
            headers=headers,
            json={"name": "auditor", "description": "audit role", "permissions": ["custom.audit"]},
        )
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.patch(
            "/api/admin/roles/auditor",
            headers=headers,
            json={"description": "audit role2", "permissions": ["users.view"]},
        )
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post(
            "/api/admin/users",
            headers=headers,
            json={"username": "ops1", "password": "Ops@12345", "roles": ["auditor"], "disabled": False},
        )
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.patch(
            "/api/admin/users/ops1",
            headers=headers,
            json={"disabled": True},
        )
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.delete("/api/admin/users/ops1", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.delete("/api/admin/roles/auditor", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.delete("/api/admin/permissions/custom.audit", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

    def test_cannot_delete_current_user(self) -> None:
        token = self._login("admin", "admin123")
        r = self.client.delete("/api/admin/users/admin", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("cannot delete current user", r.text)

    def test_users_import_rejects_large_file(self) -> None:
        token = self._login("admin", "admin123")
        too_big = b"a" * (2 * 1024 * 1024 + 1)
        files = {"files": ("big.txt", too_big, "text/plain")}

        r = self.client.post(
            "/api/users/import",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
        )
        self.assertEqual(r.status_code, 413)
        self.assertIn("file too large", r.text)

    def test_users_import_accepts_file_at_size_limit_when_service_succeeds(self) -> None:
        token = self._login("admin", "admin123")
        at_limit = b"b" * (2 * 1024 * 1024)
        files = [("files", ("ok.txt", at_limit, "text/plain"))]

        fake_resp = {
            "ok": True,
            "total_files": 1,
            "total_lines": 0,
            "created": 0,
            "skipped": 0,
            "failed": 0,
            "results": [],
        }
        with patch("app.routers.users.ldap_guard", side_effect=lambda fn: fn()):
            with patch("app.routers.users.import_users_from_legacy_txt", return_value=fake_resp):
                r = self.client.post(
                    "/api/users/import",
                    headers={"Authorization": f"Bearer {token}"},
                    files=files,
                )

        self.assertEqual(r.status_code, 200, r.text)
        payload = r.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["total_files"], 1)

    def test_users_import_rejects_total_size_over_limit(self) -> None:
        token = self._login("admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}
        blob = b"x" * (2 * 1024 * 1024)
        files = [("files", (f"f{i}.txt", blob, "text/plain")) for i in range(6)]
        r = self.client.post("/api/users/import", headers=headers, files=files)
        self.assertEqual(r.status_code, 413)
        self.assertIn("total upload size too large", r.text)

    def test_users_add_delete_and_export_routes(self) -> None:
        token = self._login("admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}

        add_resp = {
            "ok": True,
            "username": "u1",
            "created": True,
            "password_updated": False,
            "moved": False,
            "moved_to_dn": None,
            "updated_attributes": [],
            "groups_added": [],
            "groups_removed": [],
        }
        del_resp = {"ok": True, "username": "u1", "deleted": True, "dn": "CN=u1,DC=ex,DC=com"}
        csv_blob = "username,dn\nu1,CN=u1,DC=ex,DC=com\n".encode("utf-8")

        with patch("app.routers.users.ldap_guard", side_effect=lambda fn: fn()):
            with patch("app.routers.users.add_or_overwrite_user", return_value=add_resp):
                r = self.client.post(
                    "/api/users",
                    headers=headers,
                    json={
                        "username": "u1",
                        "password": "A1!pass",
                        "student_id": "1",
                        "first_name": "A",
                        "last_name": "B",
                        "groups": [],
                        "ou_path": [],
                    },
                )
                self.assertEqual(r.status_code, 200, r.text)

            with patch("app.routers.users.delete_user_by_username", return_value=del_resp):
                r = self.client.delete("/api/users/u1", headers=headers)
                self.assertEqual(r.status_code, 200, r.text)

            with patch("app.routers.users.export_users_csv", return_value=csv_blob):
                r = self.client.get("/api/users/export", headers=headers)
                self.assertEqual(r.status_code, 200, r.text)
                self.assertIn("attachment; filename=", r.headers.get("content-disposition", ""))

    def test_ou_create_permission_denied_for_viewer(self) -> None:
        self.auth.create_user("viewer2", "Viewer@123", ["viewer"], disabled=False)
        token = self._login("viewer2", "Viewer@123")
        r = self.client.post(
            "/api/ldap/ou",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Students"},
        )
        self.assertEqual(r.status_code, 403)
        self.assertIn("permission denied", r.text)

    def test_system_config_versions_routes(self) -> None:
        token = self._login("admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}

        r = self.client.get("/api/system/status", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["mode"], "ldap-only")

        r = self.client.post("/api/config/validate", headers=headers, json={"shares": []})
        self.assertEqual(r.status_code, 501)
        r = self.client.post("/api/config/apply", headers=headers, json={"shares": []})
        self.assertEqual(r.status_code, 501)

        r = self.client.get("/api/versions/", headers=headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])
        r = self.client.post("/api/versions/v1/rollback", headers=headers)
        self.assertEqual(r.status_code, 501)

    def test_ldap_read_write_routes_success_paths(self) -> None:
        token = self._login("admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}

        class _FakeSvc:
            def ping(self):
                return None

            def list_groups(self, include_members=True, include_description=True):
                _ = (include_members, include_description)
                return [{"dn": "CN=Students,DC=ex,DC=com", "cn": "Students", "members": []}]

            def build_user_group_map(self):
                return {"cn=u1,dc=ex,dc=com": ["Students"]}

            def list_users(self, view="full"):
                _ = view
                return [
                    {
                        "dn": "CN=u1,OU=Students,DC=ex,DC=com",
                        "sAMAccountName": "u1",
                        "displayName": "U1",
                    }
                ]

            def list_users_page(self, **kwargs):
                _ = kwargs
                return {"total": 1, "page": 1, "page_size": 20, "items": [{"dn": "CN=u1,DC=ex,DC=com", "sAMAccountName": "u1", "groups": []}]}

            def dashboard_summary(self, recent_window_days=3):
                _ = recent_window_days
                return {"total_users": 10, "recent_login_users": 2}

            def build_group_tree(self, root_group_cn=None):
                _ = root_group_cn
                return [{"dn": "CN=Students,DC=ex,DC=com", "cn": "Students", "users": [], "groups": []}]

            def build_ou_tree(self, include_users=True, user_view="full"):
                _ = (include_users, user_view)
                return [{"dn": "OU=Students,DC=ex,DC=com", "ou": "Students", "users": [], "children": []}]

            def find_user_dn(self, _conn, username):
                return "CN=u1,OU=Students,DC=ex,DC=com" if username == "u1" else None

            def list_user_groups(self, _conn, user_dn):
                _ = user_dn
                return [SimpleNamespace(dn="CN=Students,DC=ex,DC=com", cn="Students", members=[])]

            def create_ou(self, _conn, name, parent_dn=None):
                _ = parent_dn
                return (f"OU={name},DC=ex,DC=com", True)

            def delete_ou(self, _conn, ou_dn, recursive=False):
                _ = (ou_dn, recursive)
                return 1

            def rename_ou(self, _conn, ou_dn, new_name):
                return f"OU={new_name}," + ou_dn.split(",", 1)[1]

        fake = _FakeSvc()

        with patch("app.routers.ldap.ldap_guard", side_effect=lambda fn: fn()):
            with patch("app.routers.ldap.get_ldap_service", return_value=fake):
                with patch("app.routers.ldap._with_ldap_connection", side_effect=lambda fn: fn(fake, object())):
                    self.assertEqual(self.client.get("/api/ldap/health", headers=headers).status_code, 200)
                    self.assertEqual(self.client.get("/api/ldap/groups", headers=headers).status_code, 200)
                    self.assertEqual(self.client.get("/api/ldap/user-group-map", headers=headers).status_code, 200)
                    self.assertEqual(self.client.get("/api/ldap/users", headers=headers).status_code, 200)
                    self.assertEqual(self.client.get("/api/ldap/users-page", headers=headers).status_code, 200)
                    self.assertEqual(self.client.get("/api/ldap/dashboard-summary", headers=headers).status_code, 200)
                    self.assertEqual(self.client.get("/api/ldap/tree", headers=headers).status_code, 200)
                    self.assertEqual(self.client.get("/api/ldap/ou-tree", headers=headers).status_code, 200)
                    self.assertEqual(self.client.get("/api/ldap/users/u1/groups", headers=headers).status_code, 200)
                    self.assertEqual(
                        self.client.post("/api/ldap/ou", headers=headers, json={"name": "Students"}).status_code,
                        200,
                    )
                    self.assertEqual(
                        self.client.delete("/api/ldap/ou", headers=headers, params={"dn": "OU=Students,DC=ex,DC=com"}).status_code,
                        200,
                    )
                    self.assertEqual(
                        self.client.patch(
                            "/api/ldap/ou",
                            headers=headers,
                            json={"dn": "OU=Students,DC=ex,DC=com", "new_name": "Students2"},
                        ).status_code,
                        200,
                    )

    def test_ldap_user_groups_not_found(self) -> None:
        token = self._login("admin", "admin123")
        headers = {"Authorization": f"Bearer {token}"}

        class _FakeSvc:
            def find_user_dn(self, _conn, username):
                _ = username
                return None

        with patch("app.routers.ldap._with_ldap_connection", side_effect=lambda fn: fn(_FakeSvc(), object())):
            r = self.client.get("/api/ldap/users/nope/groups", headers=headers)
        self.assertEqual(r.status_code, 404)

    def test_ldap_create_ou_maps_parent_not_found_to_400(self) -> None:
        token = self._login("admin", "admin123")
        fake_svc = type(
            "FakeSvc",
            (),
            {"create_ou": lambda self, _conn, name, parent_dn=None: (_ for _ in ()).throw(LDAPException("parent DN not found: OU=missing,DC=ex,DC=com"))},
        )()
        with patch("app.routers.ldap._with_ldap_connection", side_effect=lambda fn: fn(fake_svc, object())):
            r = self.client.post(
                "/api/ldap/ou",
                headers={"Authorization": f"Bearer {token}"},
                json={"name": "Students", "parent_dn": "OU=missing,DC=ex,DC=com"},
            )
        self.assertEqual(r.status_code, 400)
        self.assertIn("parent DN not found", r.text)

    def test_ldap_delete_ou_maps_recursive_required_to_409(self) -> None:
        token = self._login("admin", "admin123")
        fake_svc = type(
            "FakeSvc",
            (),
            {"delete_ou": lambda self, _conn, ou_dn, recursive=False: (_ for _ in ()).throw(LDAPException("OU is not empty; recursive delete required"))},
        )()
        with patch("app.routers.ldap._with_ldap_connection", side_effect=lambda fn: fn(fake_svc, object())):
            r = self.client.delete(
                "/api/ldap/ou",
                headers={"Authorization": f"Bearer {token}"},
                params={"dn": "OU=Students,DC=ex,DC=com", "recursive": "false"},
            )
        self.assertEqual(r.status_code, 409)
        self.assertIn("recursive delete required", r.text)

    def test_ldap_rename_ou_maps_access_denied_to_403(self) -> None:
        token = self._login("admin", "admin123")
        fake_svc = type(
            "FakeSvc",
            (),
            {"rename_ou": lambda self, _conn, ou_dn, new_name: (_ for _ in ()).throw(LDAPException("insufficient access rights to rename OU: OU=Students,DC=ex,DC=com"))},
        )()
        with patch("app.routers.ldap._with_ldap_connection", side_effect=lambda fn: fn(fake_svc, object())):
            r = self.client.patch(
                "/api/ldap/ou",
                headers={"Authorization": f"Bearer {token}"},
                json={"dn": "OU=Students,DC=ex,DC=com", "new_name": "Students2"},
            )
        self.assertEqual(r.status_code, 403)
        self.assertIn("insufficient access rights", r.text)


if __name__ == "__main__":
    unittest.main()
