from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fastapi import HTTPException
from ldap3.core.exceptions import LDAPException

from app.routers.ldap import (
    _raise_create_ou_http_error,
    _raise_delete_ou_http_error,
    _raise_rename_ou_http_error,
    _with_ldap_connection,
)


class LdapRouterHelperTests(unittest.TestCase):
    def test_with_ldap_connection_executes_guarded_callback(self) -> None:
        class _Svc:
            @contextmanager
            def connection(self):
                yield "CONN"

        svc = _Svc()

        with patch("app.routers.ldap.get_ldap_service", return_value=svc):
            with patch("app.routers.ldap.ldap_guard", side_effect=lambda fn: fn()):
                out = _with_ldap_connection(lambda s, c: f"{s is svc}:{c}")

        self.assertEqual(out, "True:CONN")

    def test_create_ou_error_mapping(self) -> None:
        with self.assertRaises(HTTPException) as ctx1:
            _raise_create_ou_http_error(LDAPException("parent DN not found: OU=x,DC=ex,DC=com"))
        self.assertEqual(ctx1.exception.status_code, 400)

        with self.assertRaises(HTTPException) as ctx2:
            _raise_create_ou_http_error(LDAPException("unexpected"))
        self.assertEqual(ctx2.exception.status_code, 400)
        self.assertIn("create OU failed", str(ctx2.exception.detail))

    def test_delete_ou_error_mapping(self) -> None:
        for msg, code in [
            ("recursive delete required", 409),
            ("OU not found", 404),
            ("cannot delete base DN", 400),
            ("other", 400),
        ]:
            with self.assertRaises(HTTPException) as ctx:
                _raise_delete_ou_http_error(LDAPException(msg))
            self.assertEqual(ctx.exception.status_code, code)

    def test_rename_ou_error_mapping(self) -> None:
        for msg, code in [
            ("target DN already exists", 409),
            ("insufficient access rights", 403),
            ("OU not found", 404),
            ("cannot rename base DN", 400),
            ("other", 400),
        ]:
            with self.assertRaises(HTTPException) as ctx:
                _raise_rename_ou_http_error(LDAPException(msg))
            self.assertEqual(ctx.exception.status_code, code)


if __name__ == "__main__":
    unittest.main()
