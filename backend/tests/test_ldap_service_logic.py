from __future__ import annotations

import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from ldap3.core.exceptions import LDAPException

from app.core.settings import LdapSettings
from app.services.ldap_service import LdapService


class _Conn:
    def __init__(self) -> None:
        self.entries = []
        self.result = {"result": 0}
        self.search_calls = []
        self.add_calls = []
        self.modify_calls = []
        self.modify_dn_calls = []
        self.delete_calls = []

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return True

    def add(self, dn, object_class=None, attributes=None):
        self.add_calls.append((dn, object_class, attributes))
        return True

    def modify(self, dn, changes):
        self.modify_calls.append((dn, changes))
        return True

    def modify_dn(self, **kwargs):
        self.modify_dn_calls.append(kwargs)
        return True

    def delete(self, dn):
        self.delete_calls.append(dn)
        return True


class LdapServiceLogicTests(unittest.TestCase):
    def setUp(self) -> None:
        cfg = LdapSettings(
            host="127.0.0.1",
            port=389,
            use_ssl=False,
            start_tls=False,
            bind_user="u",
            bind_password="p",
            base_dn="DC=ex,DC=com",
        )
        self.svc = LdapService(cfg)

    def test_domain_and_users_container_resolution(self) -> None:
        self.assertEqual(self.svc._domain_from_base_dn(), "ex.com")
        self.assertEqual(self.svc._users_container_dn(), "CN=Users,DC=ex,DC=com")

        self.svc.cfg.user_upn_suffix = "corp.local"
        self.svc.cfg.user_container_dn = "OU=People,DC=ex,DC=com"
        self.assertEqual(self.svc._domain_from_base_dn(), "corp.local")
        self.assertEqual(self.svc._users_container_dn(), "OU=People,DC=ex,DC=com")

    def test_parse_ldap_timestamp_handles_filetime_epoch_and_utc_string(self) -> None:
        self.assertEqual(self.svc._parse_ldap_timestamp("0"), 0)
        self.assertEqual(self.svc._parse_ldap_timestamp("1735689600"), 1735689600000)
        self.assertEqual(self.svc._parse_ldap_timestamp("1735689600000"), 1735689600000)
        self.assertEqual(self.svc._parse_ldap_timestamp("20250101000000.0Z"), 1735689600000)

    def test_entry_helpers_and_member_reading(self) -> None:
        e = SimpleNamespace(distinguishedName="CN=x,DC=ex,DC=com", member=["A", "", "B"])
        self.assertEqual(self.svc._entry_attr(e, "distinguishedName"), "CN=x,DC=ex,DC=com")
        self.assertIsNone(self.svc._entry_attr(e, "missing"))
        self.assertEqual(self.svc._normalize_dn(" CN=X , DC=EX , DC=com "), "cn=x,dc=ex,dc=com")

        e2 = SimpleNamespace(entry_attributes_as_dict={"member;range=0-1": ["u1", "", "u2"], "single": "x"})
        self.assertEqual(self.svc._entry_attr_values_by_key(e2, "member;range=0-1"), ["u1", "u2"])
        self.assertEqual(self.svc._entry_attr_values_by_key(e2, "single"), ["x"])
        self.assertEqual(self.svc._find_range_attr_key(e2, "member"), "member;range=0-1")

        with patch.object(self.svc, "_read_all_group_members_by_range", return_value=["u1", "u2"]):
            self.assertEqual(self.svc._read_member_values(_Conn(), SimpleNamespace(distinguishedName="CN=g,DC=ex,DC=com", entry_attributes_as_dict={"member;range=0-1": ["u1"]})), ["u1", "u2"])
        self.assertEqual(self.svc._read_member_values(_Conn(), e), ["A", "B"])
        self.assertEqual(self.svc._read_member_values(_Conn(), SimpleNamespace()), [])

    def test_read_all_group_members_by_range_error_paths(self) -> None:
        conn = _Conn()
        conn.search = lambda **kwargs: False
        conn.result = {"result": 1}
        with self.assertRaises(LDAPException):
            self.svc._read_all_group_members_by_range(conn, "CN=g,DC=ex,DC=com")

        steps = [
            [SimpleNamespace(entry_attributes_as_dict={"member;range=x": ["u1"]})],
        ]
        conn = _Conn()
        conn.search = lambda **kwargs: (setattr(conn, "entries", steps.pop(0)) or True)
        with self.assertRaises(LDAPException):
            self.svc._read_all_group_members_by_range(conn, "CN=g,DC=ex,DC=com")

    def test_find_dns_and_ensure_ou_path_paths(self) -> None:
        conn = _Conn()
        conn.entries = [SimpleNamespace(distinguishedName="CN=u1,DC=ex,DC=com")]
        self.assertEqual(self.svc.find_user_dn(conn, "u1"), "CN=u1,DC=ex,DC=com")
        self.assertEqual(self.svc.find_group_dn(conn, "Students"), "CN=u1,DC=ex,DC=com")

        conn.search = lambda **kwargs: False
        conn.entries = []
        self.assertIsNone(self.svc.find_user_dn(conn, "none"))
        self.assertIsNone(self.svc.find_group_dn(conn, "none"))

        conn = _Conn()
        with patch.object(self.svc, "_entry_exists_dn", side_effect=[False, False]):
            self.assertEqual(self.svc.ensure_ou_path(conn, ["A", "B"]), "OU=B,OU=A,DC=ex,DC=com")

        conn = _Conn()
        conn.add = lambda dn, object_class=None, attributes=None: False
        conn.result = {"result": 68}
        with patch.object(self.svc, "_entry_exists_dn", return_value=False):
            self.assertEqual(self.svc.ensure_ou_path(conn, ["A"]), "OU=A,DC=ex,DC=com")

        conn.result = {"result": 50}
        with patch.object(self.svc, "_entry_exists_dn", return_value=False):
            with self.assertRaises(LDAPException):
                self.svc.ensure_ou_path(conn, ["A"])

    def test_list_users_groups_and_ping(self) -> None:
        conn = _Conn()
        with patch.object(self.svc, "_search_entries_paged", return_value=[SimpleNamespace(cn="Students", distinguishedName="CN=Students,DC=ex,DC=com")]):
            groups = self.svc.list_user_groups(conn, "CN=u1,DC=ex,DC=com")
        self.assertEqual(groups[0].cn, "Students")

        @contextmanager
        def fake_connection():
            yield conn

        with patch.object(self.svc, "connection", side_effect=fake_connection):
            with patch.object(self.svc, "_search_entries_paged", return_value=[SimpleNamespace(distinguishedName="CN=u1,DC=ex,DC=com", sAMAccountName="u1")]):
                users = self.svc.list_users(view="list")
                self.assertEqual(users[0].sAMAccountName, "u1")
            self.svc.ping()

    def test_entry_exists_dn_handles_not_found_and_error(self) -> None:
        conn = _Conn()

        conn.entries = [SimpleNamespace(distinguishedName="CN=x,DC=ex,DC=com")]
        self.assertTrue(self.svc._entry_exists_dn(conn, "CN=x,DC=ex,DC=com"))

        conn.entries = []
        conn.search = lambda **kwargs: False
        conn.result = {"result": 32}
        self.assertFalse(self.svc._entry_exists_dn(conn, "CN=none,DC=ex,DC=com"))

        conn.result = {"result": 80, "message": "server down"}
        with self.assertRaises(LDAPException):
            self.svc._entry_exists_dn(conn, "CN=boom,DC=ex,DC=com")

    def test_create_ou_paths(self) -> None:
        conn = _Conn()
        with patch.object(self.svc, "_entry_exists_dn", side_effect=[True, True]):
            dn, created = self.svc.create_ou(conn, "Students", None)
        self.assertEqual(dn, "OU=Students,DC=ex,DC=com")
        self.assertFalse(created)

        with patch.object(self.svc, "_entry_exists_dn", return_value=False):
            with self.assertRaises(LDAPException):
                self.svc.create_ou(conn, "Students", "OU=Missing,DC=ex,DC=com")

    def test_rename_ou_paths(self) -> None:
        conn = _Conn()
        conn.entries = [SimpleNamespace(objectClass=["top", "organizationalUnit"], distinguishedName="OU=A,DC=ex,DC=com")]
        self.assertEqual(self.svc.rename_ou(conn, "OU=A,DC=ex,DC=com", "A"), "OU=A,DC=ex,DC=com")

        with patch.object(self.svc, "_entry_exists_dn", return_value=False):
            conn.modify_dn = lambda **kwargs: False
            conn.result = {"result": 50}
            with self.assertRaises(LDAPException) as ctx:
                self.svc.rename_ou(conn, "OU=A,DC=ex,DC=com", "B")
        self.assertIn("insufficient access rights", str(ctx.exception))

    def test_delete_ou_non_recursive_and_recursive(self) -> None:
        conn = _Conn()

        search_states = [
            [SimpleNamespace(objectClass=["organizationalUnit"], distinguishedName="OU=A,DC=ex,DC=com")],
            [SimpleNamespace(distinguishedName="CN=child,OU=A,DC=ex,DC=com")],
        ]

        def _search_non_recursive(**kwargs):
            conn.entries = search_states.pop(0)
            return True

        conn.search = _search_non_recursive
        with self.assertRaises(LDAPException) as ctx:
            self.svc.delete_ou(conn, "OU=A,DC=ex,DC=com", recursive=False)
        self.assertIn("recursive delete required", str(ctx.exception))

        conn = _Conn()
        subtree_entries = [
            [SimpleNamespace(objectClass=["organizationalUnit"], distinguishedName="OU=A,DC=ex,DC=com")],
            [],
            [
                SimpleNamespace(distinguishedName="OU=A,DC=ex,DC=com"),
                SimpleNamespace(distinguishedName="OU=B,OU=A,DC=ex,DC=com"),
                SimpleNamespace(distinguishedName="CN=u1,OU=B,OU=A,DC=ex,DC=com"),
            ],
        ]

        def _search_recursive(**kwargs):
            conn.entries = subtree_entries.pop(0)
            return True

        conn.search = _search_recursive
        deleted = self.svc.delete_ou(conn, "OU=A,DC=ex,DC=com", recursive=True)
        self.assertEqual(deleted, 3)
        self.assertEqual(
            conn.delete_calls,
            [
                "CN=u1,OU=B,OU=A,DC=ex,DC=com",
                "OU=B,OU=A,DC=ex,DC=com",
                "OU=A,DC=ex,DC=com",
            ],
        )

        conn = _Conn()
        subtree_entries = [
            [SimpleNamespace(objectClass=["organizationalUnit"], distinguishedName="OU=A,DC=ex,DC=com")],
            [],
            [SimpleNamespace(distinguishedName="OU=A,DC=ex,DC=com")],
        ]
        conn.search = lambda **kwargs: (setattr(conn, "entries", subtree_entries.pop(0)) or True)
        conn.delete = lambda dn: False
        conn.result = {"result": 50}
        with self.assertRaises(LDAPException):
            self.svc.delete_ou(conn, "OU=A,DC=ex,DC=com", recursive=True)

    def test_update_user_profile_group_membership_helpers(self) -> None:
        conn = _Conn()
        updated = self.svc.update_user_profile(
            conn,
            user_dn="CN=u1,DC=ex,DC=com",
            student_id="123",
            first_name="Ivan",
            last_name="Ivanov",
            display_name=None,
            paid_flag=None,
        )
        self.assertIn("employeeType", updated)

        conn = _Conn()
        state = {"calls": 0}

        def _modify_paid_none(dn, changes):
            state["calls"] += 1
            if state["calls"] == 1:
                return True
            conn.result = {"result": 16}
            return False

        conn.modify = _modify_paid_none
        updated = self.svc.update_user_profile(
            conn,
            user_dn="CN=u1,DC=ex,DC=com",
            student_id="123",
            first_name="Ivan",
            last_name="Ivanov",
            display_name="Ivan Ivanov",
            paid_flag=None,
        )
        self.assertIn("employeeType", updated)

        conn = _Conn()
        conn.modify = lambda dn, changes: False
        conn.result = {"result": 20}
        self.svc.add_user_to_group(conn, "CN=u1,DC=ex,DC=com", "CN=g,DC=ex,DC=com")

        conn.result = {"result": 1, "message": "other error"}
        with self.assertRaises(LDAPException):
            self.svc.add_user_to_group(conn, "CN=u1,DC=ex,DC=com", "CN=g,DC=ex,DC=com")

        conn.result = {"result": 16}
        self.svc.remove_user_from_group(conn, "CN=u1,DC=ex,DC=com", "CN=g,DC=ex,DC=com")

        conn.result = {"result": 1, "message": "not a member"}
        self.svc.remove_user_from_group(conn, "CN=u1,DC=ex,DC=com", "CN=g,DC=ex,DC=com")

        conn.result = {"result": 1, "message": "other error"}
        with self.assertRaises(LDAPException):
            self.svc.remove_user_from_group(conn, "CN=u1,DC=ex,DC=com", "CN=g,DC=ex,DC=com")


if __name__ == "__main__":
    unittest.main()
