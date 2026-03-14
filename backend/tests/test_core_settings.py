from __future__ import annotations

import unittest

from app.core.settings import LdapSettings, _bool, _csv_list


class CoreSettingsTests(unittest.TestCase):
    def test_bool_parser(self) -> None:
        self.assertTrue(_bool("1"))
        self.assertTrue(_bool(" yes "))
        self.assertFalse(_bool("0", default=True))
        self.assertFalse(_bool("off", default=True))
        self.assertTrue(_bool("invalid", default=True))

    def test_csv_list_parser(self) -> None:
        self.assertEqual(_csv_list(None, ["*"]), ["*"])
        self.assertEqual(_csv_list(" a, ,b , c ", []), ["a", "b", "c"])

    def test_ldap_settings_normalized(self) -> None:
        cfg = LdapSettings(
            host="127.0.0.1",
            port=636,
            use_ssl=True,
            start_tls=True,
            bind_user="u",
            bind_password="p",
            base_dn="DC=ex,DC=com",
            user_container_dn="   ",
            user_upn_suffix=" corp.local ",
        )
        out = cfg.normalized()
        self.assertIs(out, cfg)
        self.assertFalse(cfg.start_tls)
        self.assertIsNone(cfg.user_container_dn)
        self.assertEqual(cfg.user_upn_suffix, "corp.local")


if __name__ == "__main__":
    unittest.main()
