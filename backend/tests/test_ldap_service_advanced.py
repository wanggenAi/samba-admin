from __future__ import annotations

import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from ldap3.core.exceptions import LDAPException

from app.core.settings import LdapSettings
from app.schemas.ldap import LdapGroup, LdapUser
from app.services.ldap_service import LdapService


class _Conn:
    def __init__(self) -> None:
        self.entries = []
        self.result = {"controls": {"1.2.840.113556.1.4.319": {"value": {"cookie": b""}}}}
        self.search_calls = []

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return True


def _make_user(dn: str, username: str, last_logon: str | None = None):
    return type(
        "U",
        (),
        {
            "dn": dn,
            "sAMAccountName": username,
            "displayName": username,
            "userPrincipalName": f"{username}@example.com",
            "givenName": username,
            "sn": "User",
            "employeeID": None,
            "employeeType": None,
            "whenCreated": None,
            "whenChanged": None,
            "lastLogon": last_logon,
            "lastLogoff": None,
            "model_dump": lambda self=None: {
                "dn": dn,
                "sAMAccountName": username,
                "displayName": username,
                "userPrincipalName": f"{username}@example.com",
                "givenName": username,
                "sn": "User",
                "employeeID": None,
                "employeeType": None,
                "whenCreated": None,
                "whenChanged": None,
                "lastLogon": last_logon,
                "lastLogoff": None,
            },
        },
    )()


class LdapServiceAdvancedTests(unittest.TestCase):
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

    def test_search_entries_paged_raises_on_failed_search(self) -> None:
        conn = _Conn()
        conn.search = lambda **kwargs: False
        conn.result = {"result": 50, "message": "error"}
        with self.assertRaises(LDAPException):
            self.svc._search_entries_paged(
                conn,  # type: ignore[arg-type]
                search_base="DC=ex,DC=com",
                search_filter="(objectClass=*)",
                attributes=["distinguishedName"],
            )

    def test_dashboard_summary_counts_recent_logins(self) -> None:
        users = [
            LdapUser(dn="CN=u1,DC=ex,DC=com", sAMAccountName="u1", lastLogon="20250101000000.0Z"),
            LdapUser(dn="CN=u2,DC=ex,DC=com", sAMAccountName="u2", lastLogon="20240101000000.0Z"),
            LdapUser(dn="CN=u3,DC=ex,DC=com", sAMAccountName="u3", lastLogon=None),
        ]
        with patch.object(self.svc, "list_users", return_value=users):
            with patch("app.services.ldap_service.time.time", return_value=1735776000):  # 2025-01-02 UTC
                result = self.svc.dashboard_summary(recent_window_days=1)

        self.assertEqual(result["total_users"], 3)
        self.assertEqual(result["recent_login_users"], 1)

    def test_list_users_page_group_filter_with_empty_members_returns_empty(self) -> None:
        users = [_make_user("CN=u1,OU=A,DC=ex,DC=com", "u1")]
        conn = _Conn()

        @contextmanager
        def fake_connection():
            yield conn

        with patch.object(self.svc, "list_users", return_value=users):
            with patch.object(self.svc, "connection", side_effect=fake_connection):
                with patch.object(self.svc, "find_group_dn", return_value="CN=G,DC=ex,DC=com"):
                    with patch.object(self.svc, "list_user_groups", return_value=[]):
                        result = self.svc.list_users_page(group_cns=["G"])

        self.assertEqual(result["total"], 0)
        self.assertEqual(result["items"], [])

    def test_build_ou_tree_with_users(self) -> None:
        ou_entries = [
            SimpleNamespace(distinguishedName="OU=Students,DC=ex,DC=com", ou="Students"),
            SimpleNamespace(distinguishedName="OU=Sub,OU=Students,DC=ex,DC=com", ou="Sub"),
        ]
        user_entries = [
            SimpleNamespace(
                distinguishedName="CN=u1,OU=Students,DC=ex,DC=com",
                sAMAccountName="u1",
                displayName="U1",
                userPrincipalName="u1@example.com",
                givenName="U",
                sn="One",
                employeeID=None,
                employeeType=None,
                whenCreated=None,
                whenChanged=None,
                lastLogon=None,
                lastLogoff=None,
            )
        ]

        @contextmanager
        def fake_connection():
            yield _Conn()

        with patch.object(self.svc, "connection", return_value=fake_connection()):
            with patch.object(self.svc, "_search_entries_paged", side_effect=[ou_entries, user_entries]):
                tree = self.svc.build_ou_tree(include_users=True, user_view="list")

        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0].ou, "Students")
        self.assertEqual(len(tree[0].users), 1)
        self.assertEqual(tree[0].users[0].sAMAccountName, "u1")
        self.assertEqual(len(tree[0].children), 1)
        self.assertEqual(tree[0].children[0].ou, "Sub")

    def test_fetch_users_by_dn_batches_queries(self) -> None:
        dns = [f"CN=u{i},DC=ex,DC=com" for i in range(25)]
        conn = _Conn()

        def _search(**kwargs):
            flt = kwargs.get("search_filter", "")
            if "u0" in flt:
                conn.entries = [SimpleNamespace(distinguishedName="CN=u0,DC=ex,DC=com", sAMAccountName="u0")]
            else:
                conn.entries = [SimpleNamespace(distinguishedName="CN=u24,DC=ex,DC=com", sAMAccountName="u24")]
            conn.search_calls.append(kwargs)
            return True

        conn.search = _search

        @contextmanager
        def fake_connection():
            yield conn

        with patch.object(self.svc, "connection", return_value=fake_connection()):
            out = self.svc._fetch_users_by_dn(dns)

        self.assertIn("cn=u0,dc=ex,dc=com", out)
        self.assertIn("cn=u24,dc=ex,dc=com", out)
        self.assertEqual(len(conn.search_calls), 2)

    def test_build_group_tree_with_root_and_cycle_guard(self) -> None:
        groups = [
            LdapGroup(dn="CN=Root,DC=ex,DC=com", cn="Root", members=["CN=Child,DC=ex,DC=com", "CN=u1,DC=ex,DC=com"]),
            LdapGroup(dn="CN=Child,DC=ex,DC=com", cn="Child", members=["CN=Root,DC=ex,DC=com"]),
        ]
        users = {"cn=u1,dc=ex,dc=com": LdapUser(dn="CN=u1,DC=ex,DC=com", sAMAccountName="u1")}

        with patch.object(self.svc, "list_groups", return_value=groups):
            with patch.object(self.svc, "_fetch_users_by_dn", return_value=users):
                root_tree = self.svc.build_group_tree(root_group_cn="Root")

        self.assertEqual(len(root_tree), 1)
        self.assertEqual(root_tree[0].cn, "Root")
        self.assertEqual(len(root_tree[0].users), 1)
        self.assertEqual(root_tree[0].users[0].sAMAccountName, "u1")
        self.assertEqual(len(root_tree[0].groups), 1)
        self.assertEqual(root_tree[0].groups[0].cn, "Child")


if __name__ == "__main__":
    unittest.main()
