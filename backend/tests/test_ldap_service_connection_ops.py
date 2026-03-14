from __future__ import annotations

import ssl
import unittest
from unittest.mock import MagicMock, patch

from ldap3.core.exceptions import LDAPException

from app.core.settings import LdapSettings
from app.services.ldap_service import LdapService


class _ConnBase:
    def __init__(self) -> None:
        self.result = {"result": 0}
        self.open_called = False
        self.start_tls_called = False
        self.bind_called = False
        self.unbind_called = False
        self.add_called = []
        self.modify_called = []
        self.modify_dn_called = []
        self.delete_called = []
        self.extend = type("E", (), {"microsoft": type("M", (), {"modify_password": lambda self, user, new_password: True})()})()

    def open(self):
        self.open_called = True

    def start_tls(self):
        self.start_tls_called = True
        return True

    def bind(self):
        self.bind_called = True
        return True

    def unbind(self):
        self.unbind_called = True

    def add(self, dn, attributes=None, object_class=None):
        self.add_called.append((dn, attributes, object_class))
        return True

    def modify(self, dn, changes):
        self.modify_called.append((dn, changes))
        return True

    def modify_dn(self, **kwargs):
        self.modify_dn_called.append(kwargs)
        return True

    def delete(self, dn):
        self.delete_called.append(dn)
        return True


class LdapServiceConnectionOpsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = LdapSettings(
            host="127.0.0.1",
            port=389,
            use_ssl=False,
            start_tls=False,
            bind_user="u",
            bind_password="p",
            base_dn="DC=ex,DC=com",
        )
        self.svc = LdapService(self.cfg)

    def test_make_tls_respects_skip_verify(self) -> None:
        self.svc.cfg.tls_skip_verify = True
        tls = self.svc._make_tls()
        self.assertEqual(tls.validate, ssl.CERT_NONE)

        self.svc.cfg.tls_skip_verify = False
        tls = self.svc._make_tls()
        self.assertEqual(tls.validate, ssl.CERT_REQUIRED)

    def test_connect_happy_path_and_connection_context(self) -> None:
        self.svc.cfg.start_tls = True
        conn = _ConnBase()

        with patch("app.services.ldap_service.ldap3.Server", return_value=object()):
            with patch("app.services.ldap_service.ldap3.Connection", return_value=conn):
                out = self.svc._connect()
                self.assertIs(out, conn)
                self.assertTrue(conn.open_called)
                self.assertTrue(conn.start_tls_called)
                self.assertTrue(conn.bind_called)

                with self.svc.connection() as c2:
                    self.assertIs(c2, conn)
                self.assertTrue(conn.unbind_called)

    def test_connect_raises_for_open_starttls_bind_failures(self) -> None:
        class _OpenFail(_ConnBase):
            def open(self):
                raise RuntimeError("boom")

        conn = _OpenFail()
        with patch("app.services.ldap_service.ldap3.Server", return_value=object()):
            with patch("app.services.ldap_service.ldap3.Connection", return_value=conn):
                with self.assertRaises(LDAPException) as ctx:
                    self.svc._connect()
        self.assertIn("socket connection failed", str(ctx.exception))

        class _TlsFail(_ConnBase):
            def start_tls(self):
                return False

        self.svc.cfg.start_tls = True
        conn = _TlsFail()
        with patch("app.services.ldap_service.ldap3.Server", return_value=object()):
            with patch("app.services.ldap_service.ldap3.Connection", return_value=conn):
                with self.assertRaises(LDAPException) as ctx_tls:
                    self.svc._connect()
        self.assertIn("start_tls failed", str(ctx_tls.exception))

        class _BindFail(_ConnBase):
            def bind(self):
                return False

        self.svc.cfg.start_tls = False
        conn = _BindFail()
        with patch("app.services.ldap_service.ldap3.Server", return_value=object()):
            with patch("app.services.ldap_service.ldap3.Connection", return_value=conn):
                with self.assertRaises(LDAPException) as ctx_bind:
                    self.svc._connect()
        self.assertIn("bind failed", str(ctx_bind.exception))

    def test_create_user_and_password_delete_update_login_paths(self) -> None:
        conn = _ConnBase()

        with patch.object(self.svc, "set_user_password") as set_pw:
            dn = self.svc.create_user(conn, "alice", "P@ssw0rd", first_name="A", last_name="B", display_name="AB")
            self.assertTrue(dn.startswith("CN=alice,"))
            set_pw.assert_called_once()

        conn = _ConnBase()
        conn.add = MagicMock(return_value=False)
        conn.result = {"result": 50}
        with self.assertRaises(LDAPException):
            self.svc.create_user(conn, "alice", "P@ssw0rd")

        conn = _ConnBase()
        conn.modify = MagicMock(return_value=False)
        conn.result = {"result": 50}
        with patch.object(self.svc, "set_user_password"):
            with self.assertRaises(LDAPException):
                self.svc.create_user(conn, "alice", "P@ssw0rd")

        conn = _ConnBase()
        self.svc.set_user_password(conn, "CN=alice,DC=ex,DC=com", "x")

        conn.extend.microsoft.modify_password = lambda user, new_password: False
        with self.assertRaises(LDAPException):
            self.svc.set_user_password(conn, "CN=alice,DC=ex,DC=com", "x")

        conn = _ConnBase()
        self.svc.delete_user(conn, "CN=alice,DC=ex,DC=com")
        conn.delete = lambda dn: False
        with self.assertRaises(LDAPException):
            self.svc.delete_user(conn, "CN=alice,DC=ex,DC=com")

        conn = _ConnBase()
        self.assertEqual(self.svc.update_user_login_identifiers(conn, "CN=alice,DC=ex,DC=com", "alice2"), ["sAMAccountName", "userPrincipalName"])
        conn.modify = lambda dn, changes: False
        with self.assertRaises(LDAPException):
            self.svc.update_user_login_identifiers(conn, "CN=alice,DC=ex,DC=com", "alice2")

    def test_move_user_to_parent_branches(self) -> None:
        conn = _ConnBase()
        same = self.svc.move_user_to_parent(conn, "CN=alice,OU=A,DC=ex,DC=com", "alice", "OU=A,DC=ex,DC=com")
        self.assertEqual(same, "CN=alice,OU=A,DC=ex,DC=com")

        conn = _ConnBase()
        with patch.object(self.svc, "_entry_exists_dn", return_value=True):
            with self.assertRaises(LDAPException) as ctx:
                self.svc.move_user_to_parent(conn, "CN=alice,OU=A,DC=ex,DC=com", "alice", "OU=B,DC=ex,DC=com")
        self.assertIn("target DN already exists", str(ctx.exception))

        conn = _ConnBase()
        with patch.object(self.svc, "_entry_exists_dn", return_value=False):
            conn.modify_dn = lambda **kwargs: False
            conn.result = {"result": 68}
            with self.assertRaises(LDAPException):
                self.svc.move_user_to_parent(conn, "CN=alice,OU=A,DC=ex,DC=com", "alice", "OU=B,DC=ex,DC=com")

            conn.result = {"result": 50}
            with self.assertRaises(LDAPException) as ctx_50:
                self.svc.move_user_to_parent(conn, "CN=alice,OU=A,DC=ex,DC=com", "alice", "OU=B,DC=ex,DC=com")
            self.assertIn("insufficient access rights", str(ctx_50.exception))


if __name__ == "__main__":
    unittest.main()
