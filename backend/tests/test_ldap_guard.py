from __future__ import annotations

import unittest

from fastapi import HTTPException
from ldap3.core.exceptions import LDAPException

from app.routers import ldap_guard


class LdapGuardTests(unittest.TestCase):
    def test_maps_connection_refused_to_503(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            ldap_guard(lambda: (_ for _ in ()).throw(LDAPException("socket connection error while opening: [Errno 61] Connection refused")))
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("LDAP server unavailable", str(ctx.exception.detail))

    def test_maps_other_ldap_error_to_500(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            ldap_guard(lambda: (_ for _ in ()).throw(LDAPException("bind failed")))
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("bind failed", str(ctx.exception.detail))

    def test_passthrough_http_exception(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            ldap_guard(lambda: (_ for _ in ()).throw(HTTPException(status_code=418, detail="teapot")))
        self.assertEqual(ctx.exception.status_code, 418)

    def test_maps_unhandled_exception_to_500(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            ldap_guard(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertEqual(ctx.exception.detail, "internal server error")


if __name__ == "__main__":
    unittest.main()
