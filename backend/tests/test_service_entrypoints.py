from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.services import get_ldap_service
from app.services.samba_service import (
    apply_config,
    get_service_status,
    list_versions,
    rollback_version,
    validate_config,
)


class ServiceEntrypointsTests(unittest.TestCase):
    def test_get_ldap_service_requires_bind_password(self) -> None:
        from app.services import settings as services_settings

        old = services_settings.ldap.bind_password
        try:
            services_settings.ldap.bind_password = ""
            with self.assertRaises(HTTPException) as ctx:
                get_ldap_service()
            self.assertEqual(ctx.exception.status_code, 400)

            services_settings.ldap.bind_password = "secret"
            with patch("app.services.LdapService") as cls:
                _ = get_ldap_service()
                cls.assert_called_once()
        finally:
            services_settings.ldap.bind_password = old

    def test_samba_service_ldap_only_mode(self) -> None:
        status = get_service_status()
        self.assertEqual(status["mode"], "ldap-only")
        self.assertFalse(status["active"])

        self.assertEqual(list_versions(), [])

        dummy_payload = object()
        with self.assertRaises(HTTPException) as ctx_validate:
            validate_config(dummy_payload)  # type: ignore[arg-type]
        self.assertEqual(ctx_validate.exception.status_code, 501)

        with self.assertRaises(HTTPException) as ctx_apply:
            apply_config(dummy_payload)  # type: ignore[arg-type]
        self.assertEqual(ctx_apply.exception.status_code, 501)

        with self.assertRaises(HTTPException) as ctx_rb:
            rollback_version("v1")
        self.assertEqual(ctx_rb.exception.status_code, 501)


if __name__ == "__main__":
    unittest.main()
