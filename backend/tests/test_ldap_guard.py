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


if __name__ == "__main__":
    unittest.main()
