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


if __name__ == "__main__":
    unittest.main()
