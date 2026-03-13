from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from app.core.settings import LdapSettings
from app.services.ldap_service import LdapService


class FakeEntry:
    def __init__(self, attrs: dict[str, object]):
        self.entry_attributes_as_dict = dict(attrs)
        for key, value in attrs.items():
            if str(key).isidentifier():
                setattr(self, str(key), value)


class FakePagedConn:
    def __init__(self) -> None:
        self.calls: list[object] = []
        self.entries: list[object] = []
        self.result: dict[str, object] = {}
        self._step = 0

    def search(self, **kwargs) -> bool:
        self.calls.append(kwargs.get("paged_cookie"))
        if self._step == 0:
            self.entries = ["first"]
            self.result = {"controls": {"1.2.840.113556.1.4.319": {"value": {"cookie": b"next"}}}}
        else:
            self.entries = ["second"]
            self.result = {"controls": {"1.2.840.113556.1.4.319": {"value": {"cookie": b""}}}}
        self._step += 1
        return True


class FakeRangeConn:
    def __init__(self, group_dn: str):
        self.group_dn = group_dn
        self.entries: list[object] = []
        self.result: dict[str, object] = {"result": 0}

    def search(self, **kwargs) -> bool:
        search_base = kwargs.get("search_base")
        attrs = kwargs.get("attributes") or []
        if search_base != self.group_dn or not attrs:
            self.entries = []
            self.result = {"result": 1}
            return False

        attr = str(attrs[0])
        if attr.startswith("member;range=0-"):
            self.entries = [FakeEntry({"member;range=0-1": ["CN=u1,DC=ex,DC=com", "CN=u2,DC=ex,DC=com"]})]
            self.result = {"result": 0}
            return True
        if attr.startswith("member;range=2-"):
            self.entries = [FakeEntry({"member;range=2-*": ["CN=u3,DC=ex,DC=com"]})]
            self.result = {"result": 0}
            return True

        self.entries = []
        self.result = {"result": 1}
        return False


class LdapServiceTests(unittest.TestCase):
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

    def test_search_entries_paged_collects_all_pages(self) -> None:
        conn = FakePagedConn()
        result = self.svc._search_entries_paged(
            conn,  # type: ignore[arg-type]
            search_base="DC=ex,DC=com",
            search_filter="(objectClass=*)",
            attributes=["distinguishedName"],
        )
        self.assertEqual(result, ["first", "second"])
        self.assertEqual(conn.calls, [None, b"next"])

    def test_list_groups_reads_full_member_range(self) -> None:
        group_dn = "CN=BigGroup,DC=ex,DC=com"
        group_entry = FakeEntry(
            {
                "cn": "BigGroup",
                "distinguishedName": group_dn,
                "member;range=0-1": ["CN=u1,DC=ex,DC=com", "CN=u2,DC=ex,DC=com"],
            }
        )
        conn = FakeRangeConn(group_dn=group_dn)

        @contextmanager
        def fake_connection():
            yield conn

        with patch.object(self.svc, "connection", return_value=fake_connection()):
            with patch.object(self.svc, "_search_entries_paged", return_value=[group_entry]):
                groups = self.svc.list_groups(include_members=True, include_description=False)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].cn, "BigGroup")
        self.assertEqual(
            groups[0].members,
            ["CN=u1,DC=ex,DC=com", "CN=u2,DC=ex,DC=com", "CN=u3,DC=ex,DC=com"],
        )

    def test_build_user_group_map_returns_sorted_groups(self) -> None:
        with patch.object(
            self.svc,
            "list_groups",
            return_value=[
                type("G", (), {"cn": "Domain Users", "members": ["CN=u1,DC=ex,DC=com"]})(),
                type("G", (), {"cn": "VPN", "members": ["CN=u1,DC=ex,DC=com", "CN=u2,DC=ex,DC=com"]})(),
            ],
        ):
            mapping = self.svc.build_user_group_map()

        self.assertEqual(mapping["cn=u1,dc=ex,dc=com"], ["Domain Users", "VPN"])
        self.assertEqual(mapping["cn=u2,dc=ex,dc=com"], ["VPN"])

    def test_list_users_page_returns_paged_items_with_groups(self) -> None:
        u1 = type(
            "U",
            (),
            {
                "dn": "CN=u1,OU=Students,DC=ex,DC=com",
                "sAMAccountName": "u1",
                "displayName": "User One",
                "userPrincipalName": "u1@example.com",
                "givenName": "User",
                "sn": "One",
                "employeeID": None,
                "employeeType": None,
                "whenCreated": None,
                "whenChanged": None,
                "lastLogon": None,
                "lastLogoff": None,
                "model_dump": lambda self=None: {
                    "dn": "CN=u1,OU=Students,DC=ex,DC=com",
                    "sAMAccountName": "u1",
                    "displayName": "User One",
                    "userPrincipalName": "u1@example.com",
                    "givenName": "User",
                    "sn": "One",
                    "employeeID": None,
                    "employeeType": None,
                    "whenCreated": None,
                    "whenChanged": None,
                    "lastLogon": None,
                    "lastLogoff": None,
                },
            },
        )()
        u2 = type(
            "U",
            (),
            {
                "dn": "CN=u2,OU=Students,DC=ex,DC=com",
                "sAMAccountName": "u2",
                "displayName": "User Two",
                "userPrincipalName": "u2@example.com",
                "givenName": "User",
                "sn": "Two",
                "employeeID": None,
                "employeeType": None,
                "whenCreated": None,
                "whenChanged": None,
                "lastLogon": None,
                "lastLogoff": None,
                "model_dump": lambda self=None: {
                    "dn": "CN=u2,OU=Students,DC=ex,DC=com",
                    "sAMAccountName": "u2",
                    "displayName": "User Two",
                    "userPrincipalName": "u2@example.com",
                    "givenName": "User",
                    "sn": "Two",
                    "employeeID": None,
                    "employeeType": None,
                    "whenCreated": None,
                    "whenChanged": None,
                    "lastLogon": None,
                    "lastLogoff": None,
                },
            },
        )()

        @contextmanager
        def fake_connection():
            yield object()

        with patch.object(self.svc, "list_users", return_value=[u1, u2]):
            with patch.object(self.svc, "connection", return_value=fake_connection()):
                with patch.object(
                    self.svc,
                    "list_user_groups",
                    side_effect=[
                        [type("G", (), {"cn": "Domain Users"})()],
                    ],
                ):
                    result = self.svc.list_users_page(page=1, page_size=1, view="list")

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["page"], 1)
        self.assertEqual(result["page_size"], 1)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["sAMAccountName"], "u1")
        self.assertEqual(result["items"][0]["groups"], ["Domain Users"])

    def test_list_users_page_supports_ou_subtree_and_lastlogon_keyword(self) -> None:
        u1 = type(
            "U",
            (),
            {
                "dn": "CN=u1,OU=Sub,OU=Students,DC=ex,DC=com",
                "sAMAccountName": "u1",
                "displayName": "User One",
                "userPrincipalName": "u1@example.com",
                "givenName": "User",
                "sn": "One",
                "employeeID": None,
                "employeeType": None,
                "whenCreated": None,
                "whenChanged": None,
                "lastLogon": "20250101000000.0Z",
                "lastLogoff": None,
                "model_dump": lambda self=None: {
                    "dn": "CN=u1,OU=Sub,OU=Students,DC=ex,DC=com",
                    "sAMAccountName": "u1",
                    "displayName": "User One",
                    "userPrincipalName": "u1@example.com",
                    "givenName": "User",
                    "sn": "One",
                    "employeeID": None,
                    "employeeType": None,
                    "whenCreated": None,
                    "whenChanged": None,
                    "lastLogon": "20250101000000.0Z",
                    "lastLogoff": None,
                },
            },
        )()
        u2 = type(
            "U",
            (),
            {
                "dn": "CN=u2,OU=Teachers,DC=ex,DC=com",
                "sAMAccountName": "u2",
                "displayName": "User Two",
                "userPrincipalName": "u2@example.com",
                "givenName": "User",
                "sn": "Two",
                "employeeID": None,
                "employeeType": None,
                "whenCreated": None,
                "whenChanged": None,
                "lastLogon": "20240101000000.0Z",
                "lastLogoff": None,
                "model_dump": lambda self=None: {
                    "dn": "CN=u2,OU=Teachers,DC=ex,DC=com",
                    "sAMAccountName": "u2",
                    "displayName": "User Two",
                    "userPrincipalName": "u2@example.com",
                    "givenName": "User",
                    "sn": "Two",
                    "employeeID": None,
                    "employeeType": None,
                    "whenCreated": None,
                    "whenChanged": None,
                    "lastLogon": "20240101000000.0Z",
                    "lastLogoff": None,
                },
            },
        )()

        @contextmanager
        def fake_connection():
            yield object()

        with patch.object(self.svc, "list_users", return_value=[u1, u2]):
            with patch.object(self.svc, "connection", return_value=fake_connection()):
                with patch.object(self.svc, "list_user_groups", return_value=[]):
                    result = self.svc.list_users_page(
                        page=1,
                        page_size=10,
                        view="dashboard",
                        ou_dn="OU=Students,DC=ex,DC=com",
                        ou_scope="subtree",
                        keyword="20250101",
                    )

        self.assertEqual(result["total"], 1)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["sAMAccountName"], "u1")

    def test_list_users_page_supports_multi_ou_or_in_subtree_mode(self) -> None:
        u1 = type(
            "U",
            (),
            {
                "dn": "CN=u1,OU=bb,OU=aa,DC=ex,DC=com",
                "sAMAccountName": "u1",
                "displayName": "User One",
                "userPrincipalName": "u1@example.com",
                "givenName": "User",
                "sn": "One",
                "employeeID": None,
                "employeeType": None,
                "whenCreated": None,
                "whenChanged": None,
                "lastLogon": None,
                "lastLogoff": None,
                "model_dump": lambda self=None: {
                    "dn": "CN=u1,OU=bb,OU=aa,DC=ex,DC=com",
                    "sAMAccountName": "u1",
                    "displayName": "User One",
                    "userPrincipalName": "u1@example.com",
                    "givenName": "User",
                    "sn": "One",
                    "employeeID": None,
                    "employeeType": None,
                    "whenCreated": None,
                    "whenChanged": None,
                    "lastLogon": None,
                    "lastLogoff": None,
                },
            },
        )()
        u2 = type(
            "U",
            (),
            {
                "dn": "CN=u2,OU=bb123124,OU=aa,DC=ex,DC=com",
                "sAMAccountName": "u2",
                "displayName": "User Two",
                "userPrincipalName": "u2@example.com",
                "givenName": "User",
                "sn": "Two",
                "employeeID": None,
                "employeeType": None,
                "whenCreated": None,
                "whenChanged": None,
                "lastLogon": None,
                "lastLogoff": None,
                "model_dump": lambda self=None: {
                    "dn": "CN=u2,OU=bb123124,OU=aa,DC=ex,DC=com",
                    "sAMAccountName": "u2",
                    "displayName": "User Two",
                    "userPrincipalName": "u2@example.com",
                    "givenName": "User",
                    "sn": "Two",
                    "employeeID": None,
                    "employeeType": None,
                    "whenCreated": None,
                    "whenChanged": None,
                    "lastLogon": None,
                    "lastLogoff": None,
                },
            },
        )()
        u3 = type(
            "U",
            (),
            {
                "dn": "CN=u3,OU=other,OU=aa,DC=ex,DC=com",
                "sAMAccountName": "u3",
                "displayName": "User Three",
                "userPrincipalName": "u3@example.com",
                "givenName": "User",
                "sn": "Three",
                "employeeID": None,
                "employeeType": None,
                "whenCreated": None,
                "whenChanged": None,
                "lastLogon": None,
                "lastLogoff": None,
                "model_dump": lambda self=None: {
                    "dn": "CN=u3,OU=other,OU=aa,DC=ex,DC=com",
                    "sAMAccountName": "u3",
                    "displayName": "User Three",
                    "userPrincipalName": "u3@example.com",
                    "givenName": "User",
                    "sn": "Three",
                    "employeeID": None,
                    "employeeType": None,
                    "whenCreated": None,
                    "whenChanged": None,
                    "lastLogon": None,
                    "lastLogoff": None,
                },
            },
        )()

        @contextmanager
        def fake_connection():
            yield object()

        with patch.object(self.svc, "list_users", return_value=[u1, u2, u3]):
            with patch.object(self.svc, "connection", return_value=fake_connection()):
                with patch.object(self.svc, "list_user_groups", return_value=[]):
                    result = self.svc.list_users_page(
                        page=1,
                        page_size=20,
                        view="list",
                        ou_dns=[
                            "OU=bb,OU=aa,DC=ex,DC=com",
                            "OU=bb123124,OU=aa,DC=ex,DC=com",
                        ],
                        ou_scope="subtree",
                    )

        usernames = [item["sAMAccountName"] for item in result["items"]]
        self.assertEqual(result["total"], 2)
        self.assertEqual(set(usernames), {"u1", "u2"})

if __name__ == "__main__":
    unittest.main()
