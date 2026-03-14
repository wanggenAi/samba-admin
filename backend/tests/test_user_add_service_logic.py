from __future__ import annotations

import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from ldap3.core.exceptions import LDAPException

from app.schemas.users import UserAddRequest
from app.services.users.user_add_service import (
    _build_username_seeds,
    _find_available_username,
    _normalize_username_seed,
    _parent_dn_from_dn,
    _add_user_groups,
    _raise_move_user_http_error,
    _sync_user_groups,
    _username_from_dn,
    add_or_overwrite_user,
)


class _Svc:
    def __init__(self) -> None:
        self.calls = []
        self._user_dns = {}

    @contextmanager
    def connection(self):
        yield object()

    def ensure_ou_path(self, _conn, ou_path):
        self.calls.append(("ensure_ou_path", list(ou_path)))
        return "OU=Students,DC=ex,DC=com"

    def find_user_dn(self, _conn, username):
        return self._user_dns.get(username)

    def create_user(self, _conn, username, password, parent_dn=None, first_name=None, last_name=None, display_name=None):
        self.calls.append(("create_user", username, password, parent_dn, first_name, last_name, display_name))
        return f"CN={username},{parent_dn or 'CN=Users,DC=ex,DC=com'}"

    def move_user_to_parent(self, _conn, user_dn, username, parent_dn):
        self.calls.append(("move_user_to_parent", user_dn, username, parent_dn))
        return f"CN={username},{parent_dn}"

    def update_user_login_identifiers(self, _conn, user_dn, username):
        self.calls.append(("update_user_login_identifiers", user_dn, username))
        return ["sAMAccountName", "userPrincipalName"]

    def set_user_password(self, _conn, user_dn, password):
        self.calls.append(("set_user_password", user_dn, password))

    def update_user_profile(self, **kwargs):
        self.calls.append(("update_user_profile", kwargs["user_dn"]))
        return ["displayName", "givenName", "sn", "employeeID"]

    def find_group_dn(self, _conn, group_cn):
        return f"CN={group_cn},DC=ex,DC=com" if group_cn != "Missing" else None

    def add_user_to_group(self, _conn, user_dn, group_dn):
        self.calls.append(("add_user_to_group", user_dn, group_dn))

    def remove_user_from_group(self, _conn, user_dn, group_dn):
        self.calls.append(("remove_user_from_group", user_dn, group_dn))

    def list_user_groups(self, _conn, _user_dn):
        return [SimpleNamespace(dn="CN=OldGroup,DC=ex,DC=com", cn="OldGroup")]


class UserAddServiceLogicTests(unittest.TestCase):
    def _payload(self, **kwargs):
        base = {
            "username": "alice",
            "password": "A1!pass",
            "student_id": "2026001",
            "first_name": "Alice",
            "last_name": "Smith",
            "display_name": "Alice Smith",
            "groups": ["Students"],
            "ou_path": ["Students"],
            "sync_groups": False,
        }
        base.update(kwargs)
        return UserAddRequest(**base)

    def test_add_user_groups_raises_when_group_missing(self) -> None:
        svc = _Svc()
        with self.assertRaises(HTTPException) as ctx:
            _add_user_groups(svc, object(), "CN=alice,DC=ex,DC=com", ["Missing"])
        self.assertEqual(ctx.exception.status_code, 400)

    def test_username_and_dn_helpers(self) -> None:
        self.assertEqual(_username_from_dn("CN=alice,OU=A,DC=ex,DC=com"), "alice")
        self.assertEqual(_username_from_dn("OU=A,DC=ex,DC=com"), "")
        self.assertEqual(_parent_dn_from_dn("CN=alice,OU=A,DC=ex,DC=com"), "OU=A,DC=ex,DC=com")
        with self.assertRaises(HTTPException):
            _parent_dn_from_dn("invalid")

    def test_username_seed_helpers(self) -> None:
        self.assertEqual(_normalize_username_seed("  Äli_ce-01  "), "ali_ce-01")
        seeds = _build_username_seeds("Alice", "Smith", "2026")
        self.assertIn("alice.smith", seeds)
        self.assertIn("2026", seeds)

    def test_find_available_username(self) -> None:
        class _TakenSvc:
            def __init__(self):
                self.calls = 0

            def find_user_dn(self, _conn, username):
                self.calls += 1
                return "dn" if username == "alice" else None

        svc = _TakenSvc()
        self.assertEqual(_find_available_username(object(), svc, "alice"), "alice1")
        with self.assertRaises(HTTPException):
            _find_available_username(object(), svc, "   ")

    def test_sync_user_groups_adds_and_removes(self) -> None:
        svc = _Svc()
        groups_added, groups_removed = _sync_user_groups(
            svc,
            object(),
            "CN=alice,DC=ex,DC=com",
            ["Students"],
        )
        self.assertEqual(groups_added, ["Students"])
        self.assertEqual(groups_removed, ["OldGroup"])

    def test_raise_move_user_http_error_mappings(self) -> None:
        with self.assertRaises(HTTPException) as ctx_conflict:
            _raise_move_user_http_error("alice", ["Students"], LDAPException("target DN already exists"))
        self.assertEqual(ctx_conflict.exception.status_code, 409)

        with self.assertRaises(HTTPException) as ctx_forbidden:
            _raise_move_user_http_error("alice", ["Students"], LDAPException("insufficient access rights"))
        self.assertEqual(ctx_forbidden.exception.status_code, 403)

        with self.assertRaises(HTTPException) as ctx_bad:
            _raise_move_user_http_error("alice", ["Students"], LDAPException("anything else"))
        self.assertEqual(ctx_bad.exception.status_code, 400)

    def test_add_or_overwrite_user_create_flow(self) -> None:
        svc = _Svc()
        with patch("app.services.users.user_add_service.get_ldap_service", return_value=svc):
            result = add_or_overwrite_user(self._payload())

        self.assertTrue(result.created)
        self.assertFalse(result.password_updated)
        self.assertEqual(result.username, "alice")
        self.assertEqual(result.groups_added, ["Students"])

    def test_add_or_overwrite_user_create_requires_password(self) -> None:
        svc = _Svc()
        payload = self._payload(password=None)
        with patch("app.services.users.user_add_service.get_ldap_service", return_value=svc):
            with self.assertRaises(HTTPException) as ctx:
                add_or_overwrite_user(payload)
        self.assertEqual(ctx.exception.status_code, 422)

    def test_add_or_overwrite_user_update_conflict_and_move_error(self) -> None:
        svc = _Svc()
        svc._user_dns = {
            "alice": "CN=alice,CN=Users,DC=ex,DC=com",
            "alice2": "CN=alice2,CN=Users,DC=ex,DC=com",
        }

        with patch("app.services.users.user_add_service.get_ldap_service", return_value=svc):
            with self.assertRaises(HTTPException) as ctx:
                add_or_overwrite_user(self._payload(username="alice2", source_username="alice"))
        self.assertEqual(ctx.exception.status_code, 409)

        svc = _Svc()
        svc._user_dns = {"alice": "CN=alice,CN=Users,DC=ex,DC=com", "alice2": None}
        svc.move_user_to_parent = lambda _conn, user_dn, username, parent_dn: (_ for _ in ()).throw(
            LDAPException("insufficient access rights")
        )
        with patch("app.services.users.user_add_service.get_ldap_service", return_value=svc):
            with self.assertRaises(HTTPException) as ctx_move:
                add_or_overwrite_user(self._payload(username="alice2", source_username="alice"))
        self.assertEqual(ctx_move.exception.status_code, 403)

    def test_add_or_overwrite_user_update_sync_groups_and_password(self) -> None:
        svc = _Svc()
        svc._user_dns = {"alice": "CN=alice,CN=Users,DC=ex,DC=com"}
        payload = self._payload(password="NewP@ss1", sync_groups=True, groups=["Students"])

        with patch("app.services.users.user_add_service.get_ldap_service", return_value=svc):
            result = add_or_overwrite_user(payload)

        self.assertFalse(result.created)
        self.assertTrue(result.password_updated)
        self.assertIn("Students", result.groups_added)
        self.assertIn("OldGroup", result.groups_removed)


if __name__ == "__main__":
    unittest.main()
