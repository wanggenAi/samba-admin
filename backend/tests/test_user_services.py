from __future__ import annotations

import asyncio
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fastapi import HTTPException

from app.routers.users import _read_upload_with_limit
from app.schemas.ldap import LdapGroup, LdapUser
from app.schemas.users import UserAddRequest
from app.services.users import user_add_service
from app.services.users.user_delete_service import delete_user_by_username
from app.services.users.user_import_export_service import (
    _build_legacy_username_seed,
    _decode_legacy_text,
    _entry_attr,
    _extract_group_token,
    _extract_import_records,
    _normalize_dn,
    _normalize_for_compare,
    _normalize_spaces,
    _parent_dn,
    _resolve_import_username,
    _split_person_name,
    _transliterate_ru,
    _username_token,
    _user_name_matches,
    _parse_group_parts,
    _password,
    _extract_ou_path,
    export_users_csv,
    import_users_from_legacy_txt,
)


class _FakeUploadFile:
    def __init__(self, filename: str, chunks: list[bytes]) -> None:
        self.filename = filename
        self._chunks = chunks
        self.closed = False

    async def read(self, _size: int) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.pop(0)

    async def close(self) -> None:
        self.closed = True


class _FakeConn:
    pass


class _FakeSvc:
    def __init__(self, *, user_dn: str | None = None) -> None:
        self._user_dn = user_dn

    @contextmanager
    def connection(self):
        yield _FakeConn()

    def find_user_dn(self, _conn, _username: str):
        return self._user_dn

    def delete_user(self, _conn, _user_dn: str):
        return None


class _FakeDeleteFailSvc(_FakeSvc):
    def delete_user(self, _conn, _user_dn: str):
        from ldap3.core.exceptions import LDAPException

        raise LDAPException("delete failed")


class _FakeImportSvc:
    def __init__(self) -> None:
        self.created = []
        self.group_added = []
        self.profile_updates = []

    @contextmanager
    def connection(self):
        yield _FakeConn()

    def find_group_dn(self, _conn, group_cn: str):
        return f"CN={group_cn},DC=ex,DC=com"

    def ensure_ou_path(self, _conn, ou_path):
        return "OU=" + ",OU=".join(reversed(ou_path)) + ",DC=ex,DC=com"

    def create_user(self, _conn, username, password, parent_dn=None, first_name=None, last_name=None, display_name=None):
        self.created.append((username, password, parent_dn, first_name, last_name, display_name))
        return f"CN={username},{parent_dn}"

    def add_user_to_group(self, _conn, user_dn, group_dn):
        self.group_added.append((user_dn, group_dn))

    def update_user_profile(
        self,
        conn,
        user_dn,
        student_id,
        first_name,
        last_name,
        display_name,
        paid_flag,
    ):
        self.profile_updates.append(
            {
                "user_dn": user_dn,
                "student_id": student_id,
                "first_name": first_name,
                "last_name": last_name,
                "display_name": display_name,
                "paid_flag": paid_flag,
            }
        )
        return ["displayName", "givenName", "sn", "employeeID", "employeeType"]


class UserServicesTests(unittest.TestCase):
    def test_read_upload_with_limit_rejects_oversize(self) -> None:
        upload = _FakeUploadFile("big.txt", [b"a" * 6, b"b" * 6])
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(_read_upload_with_limit(upload, max_size=10))
        self.assertEqual(ctx.exception.status_code, 413)
        self.assertIn("file too large", str(ctx.exception.detail))

    def test_build_legacy_username_seed_handles_russian_names(self) -> None:
        seed = _build_legacy_username_seed(last_name="Иванов", first_name="Иван Иванович")
        self.assertEqual(seed, "ivaniviv")

    def test_decode_legacy_text_supports_cp1251(self) -> None:
        raw = "Группа МС-63/24".encode("cp1251")
        text = _decode_legacy_text(raw)
        self.assertIn("Группа", text)

    def test_helper_normalizers_and_extractors(self) -> None:
        self.assertEqual(_normalize_spaces("  a   b "), "a b")
        self.assertEqual(_normalize_for_compare("  A   B "), "a b")
        self.assertEqual(_transliterate_ru("Ёж"), "Ezh")
        self.assertEqual(_username_token("Иванов-Петров"), "ivanovpetrov")
        self.assertEqual(_extract_ou_path("CN=u,OU=bb,OU=aa,DC=ex,DC=com"), "aa > bb")
        self.assertEqual(_parent_dn("CN=u,OU=aa,DC=ex,DC=com"), "OU=aa,DC=ex,DC=com")
        self.assertEqual(_parent_dn("invalid"), "")
        self.assertEqual(_normalize_dn(" CN=u , DC=EX , DC=com "), "cn=u,dc=ex,dc=com")

    def test_entry_attr_and_split_person_name(self) -> None:
        entry = type("E", (), {"givenName": " Ivan ", "sn": "[]"})
        self.assertEqual(_entry_attr(entry, "givenName"), "Ivan")
        self.assertIsNone(_entry_attr(entry, "sn"))
        self.assertIsNone(_entry_attr(entry, "missing"))

        self.assertEqual(_split_person_name("Иванов Иван"), ("Иван", "Иванов"))
        with self.assertRaises(ValueError):
            _split_person_name("Иванов")

    def test_extract_group_token_requires_marker(self) -> None:
        with self.assertRaises(ValueError):
            _extract_group_token("Иванов Иван")

    def test_extract_import_records_parses_real_block_format(self) -> None:
        text = "\n".join(
            [
                "ФЭИС 3 курс",
                "группа Э-62",
                "5.",
                "Гутик Павел Олегович",
                "$",
                "230385",
                "18.",
                "Мисак Артём Леонидович",
                "$",
                "230398",
            ]
        )
        records = _extract_import_records(text)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].raw_line, "Гутик Павел Олегович")
        self.assertEqual(records[0].paid_flag, "$")
        self.assertEqual(records[0].student_id, "230385")
        self.assertEqual(records[1].raw_line, "Мисак Артём Леонидович")
        self.assertEqual(records[1].paid_flag, "$")
        self.assertEqual(records[1].student_id, "230398")

    def test_user_name_matches_and_resolve_import_username(self) -> None:
        class _ConnForName:
            def __init__(self, has_match=True):
                self.entries = []
                self.has_match = has_match

            def search(self, **kwargs):
                if not self.has_match:
                    self.entries = []
                    return False
                self.entries = [type("E", (), {"givenName": "Иван", "sn": "Иванов"})()]
                return True

        conn_ok = _ConnForName(has_match=True)
        self.assertTrue(_user_name_matches(conn_ok, "CN=u1,DC=ex,DC=com", "иван", "иванов"))

        conn_no = _ConnForName(has_match=False)
        self.assertFalse(_user_name_matches(conn_no, "CN=u1,DC=ex,DC=com", "Иван", "Иванов"))

        class _Svc:
            def __init__(self):
                self.calls = 0

            def find_user_dn(self, _conn, username):
                self.calls += 1
                if self.calls == 1:
                    return "CN=existing,DC=ex,DC=com"
                return None

        with patch("app.services.users.user_import_export_service._user_name_matches", return_value=True):
            username, exists = _resolve_import_username(object(), _Svc(), "ivan", "Иван", "Иванов")
            self.assertEqual(username, "ivan")
            self.assertTrue(exists)

        username, exists = _resolve_import_username(_ConnForName(has_match=False), _Svc(), "ivan", "Иван", "Иванов")
        self.assertEqual(username, "ivan1")
        self.assertFalse(exists)

    def test_parse_group_parts_rejects_unknown_code(self) -> None:
        with self.assertRaises(ValueError):
            _parse_group_parts("XX-24")

    def test_password_length_is_clamped_and_complex(self) -> None:
        p1 = _password(1)
        p2 = _password(1000)
        self.assertEqual(len(p1), 8)
        self.assertEqual(len(p2), 64)
        self.assertRegex(p1, r"[a-z]")
        self.assertRegex(p1, r"[A-Z]")
        self.assertRegex(p1, r"[0-9]")

    def test_import_users_requires_files(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            import_users_from_legacy_txt([])
        self.assertEqual(ctx.exception.status_code, 400)

    def test_import_users_marks_file_parse_error_for_missing_group(self) -> None:
        fake_svc = _FakeImportSvc()
        with patch("app.services.users.user_import_export_service.get_ldap_service", return_value=fake_svc):
            result = import_users_from_legacy_txt([("bad.txt", "Иванов Иван".encode("utf-8"))], default_group_cn=None)

        self.assertEqual(result.total_files, 1)
        self.assertEqual(result.created, 0)
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.results[0].status, "failed")
        self.assertIn("file parse failed", result.results[0].message)

    def test_import_users_full_flow_created_skipped_failed(self) -> None:
        fake_svc = _FakeImportSvc()
        raw_text = "\n".join(
            [
                "Группа МС-63/24",
                "1.",
                "Иванов Иван",
                "$",
                "230385",
                "2.",
                "Петров",
                "$",
                "230399",
                "3.",
                "Сидоров Сидор",
                "230400",
            ]
        ).encode("utf-8")

        # 1st line created, 2nd invalid name -> failed, 3rd skipped(existing user)
        side_effect = [("ivaniv", False), ("sidosi", True)]
        with patch("app.services.users.user_import_export_service.get_ldap_service", return_value=fake_svc):
            with patch("app.services.users.user_import_export_service._resolve_import_username", side_effect=side_effect):
                result = import_users_from_legacy_txt([("ok.txt", raw_text)], default_group_cn="Students", password_length=10)

        self.assertEqual(result.total_files, 1)
        self.assertEqual(result.total_lines, 3)
        self.assertEqual(result.created, 1)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.failed, 1)
        statuses = [x.status for x in result.results]
        self.assertEqual(statuses, ["created", "failed", "skipped"])
        self.assertEqual(len(fake_svc.created), 1)
        self.assertEqual(len(fake_svc.group_added), 1)
        self.assertEqual(len(fake_svc.profile_updates), 1)
        self.assertEqual(fake_svc.profile_updates[0]["student_id"], "230385")
        self.assertEqual(fake_svc.profile_updates[0]["paid_flag"], "$")

    def test_import_users_allows_row_when_student_id_missing(self) -> None:
        fake_svc = _FakeImportSvc()
        raw_text = "\n".join(
            [
                "Группа ИИ-2025",
                "1.",
                "Орлов Дмитрий",
                "$",
                "2.",
                "Федорова Ольга",
                "230502",
            ]
        ).encode("utf-8")

        with patch("app.services.users.user_import_export_service.get_ldap_service", return_value=fake_svc):
            with patch(
                "app.services.users.user_import_export_service._resolve_import_username",
                return_value=("fedool", False),
            ):
                result = import_users_from_legacy_txt([("ii.txt", raw_text)], default_group_cn="Students", password_length=10)

        self.assertEqual(result.total_lines, 2)
        self.assertEqual(result.created, 2)
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.results[0].status, "created")
        self.assertEqual(result.results[1].status, "created")
        self.assertIsNone(fake_svc.profile_updates[0]["student_id"])
        self.assertEqual(fake_svc.profile_updates[0]["paid_flag"], "$")
        self.assertEqual(fake_svc.profile_updates[1]["student_id"], "230502")

    def test_delete_user_rejects_blank_and_protected(self) -> None:
        with self.assertRaises(HTTPException) as ctx_blank:
            delete_user_by_username("   ")
        self.assertEqual(ctx_blank.exception.status_code, 400)

        with self.assertRaises(HTTPException) as ctx_krbtgt:
            delete_user_by_username("KrBtGt")
        self.assertEqual(ctx_krbtgt.exception.status_code, 403)

    def test_delete_user_success_path(self) -> None:
        svc = _FakeSvc(user_dn="CN=alice,DC=ex,DC=com")
        with patch("app.services.users.user_delete_service.get_ldap_service", return_value=svc):
            res = delete_user_by_username("alice")
        self.assertTrue(res.deleted)
        self.assertEqual(res.dn, "CN=alice,DC=ex,DC=com")

    def test_delete_user_not_found_and_ldap_error(self) -> None:
        svc = _FakeSvc(user_dn=None)
        with patch("app.services.users.user_delete_service.get_ldap_service", return_value=svc):
            with self.assertRaises(HTTPException) as ctx_nf:
                delete_user_by_username("alice")
        self.assertEqual(ctx_nf.exception.status_code, 404)

        svc = _FakeDeleteFailSvc(user_dn="CN=alice,DC=ex,DC=com")
        with patch("app.services.users.user_delete_service.get_ldap_service", return_value=svc):
            with self.assertRaises(HTTPException) as ctx_bad:
                delete_user_by_username("alice")
        self.assertEqual(ctx_bad.exception.status_code, 400)

    def test_export_users_csv_filters_by_group_and_keyword(self) -> None:
        users = [
            LdapUser(
                dn="CN=alice,OU=Students,DC=ex,DC=com",
                sAMAccountName="alice",
                givenName="Alice",
                sn="A",
                displayName="Alice A",
                userPrincipalName="alice@example.com",
            ),
            LdapUser(
                dn="CN=bob,OU=Teachers,DC=ex,DC=com",
                sAMAccountName="bob",
                givenName="Bob",
                sn="B",
                displayName="Bob B",
                userPrincipalName="bob@example.com",
            ),
        ]
        groups = [
            LdapGroup(
                dn="CN=Students,DC=ex,DC=com",
                cn="Students",
                members=["CN=alice,OU=Students,DC=ex,DC=com"],
            )
        ]
        fake_svc = type("Svc", (), {"list_users": lambda self: users, "list_groups": lambda self: groups})()

        with patch("app.services.users.user_import_export_service.get_ldap_service", return_value=fake_svc):
            raw = export_users_csv(keyword="alice", group_cns=["students"])

        text = raw.decode("utf-8-sig")
        self.assertIn("alice", text)
        self.assertNotIn("bob", text)

    def test_resolve_create_username_allocates_suffix_when_requested_exists(self) -> None:
        class _Svc:
            def find_user_dn(self, _conn, username: str):
                return "dn" if username == "john" else None

        payload = UserAddRequest(
            username="john",
            password="x",
            student_id="1",
            first_name="John",
            last_name="Doe",
            groups=[],
            ou_path=[],
        )
        username = user_add_service._resolve_create_username(_FakeConn(), _Svc(), payload)
        self.assertEqual(username, "john1")


if __name__ == "__main__":
    unittest.main()
