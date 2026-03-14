import unittest

from pydantic import ValidationError

from app.schemas.users import UserAddRequest


class UserSchemaTests(unittest.TestCase):
    def _base_payload(self):
        return {
            "username": "u10001",
            "password": "Test@123456",
            "student_id": "2026001",
            "first_name": "Ivan",
            "last_name": "Ivanov",
            "display_name": "Ivan Ivanov",
            "groups": ["Students"],
            "ou_path": ["Students", "ms", "63/24"],
        }

    def test_accepts_single_ou_path_segments(self):
        model = UserAddRequest(**self._base_payload())
        self.assertEqual(model.ou_path, ["Students", "ms", "63/24"])

    def test_rejects_dn_fragment_in_ou_path(self):
        payload = self._base_payload()
        payload["ou_path"] = ["OU=Students,DC=evms,DC=bstu,DC=edu"]
        with self.assertRaises(ValidationError):
            UserAddRequest(**payload)

    def test_rejects_invalid_paid_flag_and_too_deep_ou(self):
        payload = self._base_payload()
        payload["paid_flag"] = "X"
        with self.assertRaises(ValidationError):
            UserAddRequest(**payload)

        payload = self._base_payload()
        payload["ou_path"] = ["x"] * 65
        with self.assertRaises(ValidationError):
            UserAddRequest(**payload)

    def test_normalizes_groups_and_optional_fields(self):
        payload = self._base_payload()
        payload["groups"] = [" Students ", "students", "", "VPN"]
        payload["username"] = "  user1  "
        payload["display_name"] = "  "
        payload["password"] = "   P@ss   "
        model = UserAddRequest(**payload)
        self.assertEqual(model.username, "user1")
        self.assertIsNone(model.display_name)
        self.assertEqual(model.password, "P@ss")
        self.assertEqual(model.groups, ["Students", "VPN"])


if __name__ == "__main__":
    unittest.main()
