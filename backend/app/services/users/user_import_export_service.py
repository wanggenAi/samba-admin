from __future__ import annotations

import csv
import io
import re
import secrets
import string
from typing import Iterable, Optional

import ldap3
from fastapi import HTTPException
from ldap3.core.exceptions import LDAPException

from ...schemas.users import UserImportItemResult, UserImportResponse
from .. import get_ldap_service
from ..ldap_service import LdapService

MAX_USERNAME_LEN = 64
DEFAULT_PASSWORD_LENGTH = 12
GROUP_CODE_MAP = {
    "МС": "ms",
    "ПЭ": "pe",
    "Э": "e",
    "КС": "ks",
    "ИИ": "ii",
}
# Keep old grep-style behavior: pure Russian letters + spaces only.
RUS_NAME_LINE_RE = re.compile(r"^[А-Яа-яЁё ]+$")

# Basic Russian transliteration map for deterministic username generation.
_RU_LAT_MAP = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def _entry_attr(entry: object, attr: str) -> Optional[str]:
    if not hasattr(entry, attr):
        return None
    value = str(getattr(entry, attr, "")).strip()
    if not value or value == "[]":
        return None
    return value


def _normalize_spaces(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _normalize_for_compare(value: str) -> str:
    return _normalize_spaces(value).lower()


def _transliterate_ru(value: str) -> str:
    out: list[str] = []
    for ch in str(value or ""):
        low = ch.lower()
        mapped = _RU_LAT_MAP.get(low)
        if mapped is None:
            out.append(ch)
            continue
        if ch.isupper() and mapped:
            out.append(mapped[0].upper() + mapped[1:])
        else:
            out.append(mapped)
    return "".join(out)


def _username_token(value: str) -> str:
    translit = _transliterate_ru(value)
    compact = translit.replace("'", "")
    return re.sub(r"[^a-zA-Z0-9]+", "", compact).lower()


def _build_legacy_username_seed(last_name: str, first_name: str) -> str:
    last_token = _username_token(last_name)
    first_parts = [x for x in _normalize_spaces(first_name).split(" ") if x]

    seed = last_token[:4]
    for part in first_parts:
        seed += _username_token(part)[:2]

    seed = seed.strip()[:MAX_USERNAME_LEN]
    return seed or "user"


def _decode_legacy_text(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1251", "koi8-r"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin1", errors="replace")


def _extract_group_token(text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.search(r"(?i)\bгруппа\b\s*[:\-]?\s*([^\s]+)", line)
        if m:
            return m.group(1).strip()
    raise ValueError("group marker not found (expected line containing 'группа XXX-YYY')")


def _parse_group_parts(group_token: str) -> tuple[str, str]:
    token = _normalize_spaces(group_token)
    if "-" not in token:
        raise ValueError(f"invalid group token '{token}' (expected CODE-NUMBER)")

    raw_code, raw_number = token.split("-", 1)
    code = GROUP_CODE_MAP.get(raw_code.strip().upper())
    if not code:
        raise ValueError(f"unknown group code '{raw_code}'")

    number = _normalize_spaces(_transliterate_ru(raw_number)).replace(" ", "")
    if not number:
        raise ValueError(f"invalid group number in '{token}'")

    return code, number


def _extract_name_lines(text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for idx, raw in enumerate(text.splitlines(), start=1):
        line = _normalize_spaces(raw)
        if not line:
            continue
        if line in {"П", "Бюджет"}:
            continue
        if "группа" in line.lower():
            continue
        if not RUS_NAME_LINE_RE.fullmatch(line):
            continue
        out.append((idx, line))
    return out


def _split_person_name(raw_line: str) -> tuple[str, str]:
    parts = [x for x in _normalize_spaces(raw_line).split(" ") if x]
    if len(parts) < 2:
        raise ValueError("name line must include last name and first name")
    last_name = parts[0]
    first_name = " ".join(parts[1:])
    return first_name, last_name


def _password(length: int) -> str:
    size = max(8, min(int(length), 64))
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    symbols = "!@#$%*+-_"

    chars = [
        secrets.choice(lower),
        secrets.choice(upper),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]
    alphabet = lower + upper + digits + symbols
    chars.extend(secrets.choice(alphabet) for _ in range(size - len(chars)))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _user_name_matches(conn: ldap3.Connection, user_dn: str, first_name: str, last_name: str) -> bool:
    ok = conn.search(
        search_base=user_dn,
        search_filter="(objectClass=*)",
        search_scope=ldap3.BASE,
        attributes=["givenName", "sn"],
    )
    if not ok or not conn.entries:
        return False

    entry = conn.entries[0]
    existing_first = _entry_attr(entry, "givenName") or ""
    existing_last = _entry_attr(entry, "sn") or ""
    return (
        _normalize_for_compare(existing_first) == _normalize_for_compare(first_name)
        and _normalize_for_compare(existing_last) == _normalize_for_compare(last_name)
    )


def _resolve_import_username(
    conn: ldap3.Connection,
    svc: LdapService,
    base: str,
    first_name: str,
    last_name: str,
) -> tuple[str, bool]:
    seed = (base or "").strip()[:MAX_USERNAME_LEN] or "user"
    for i in range(0, 10000):
        if i == 0:
            candidate = seed
        else:
            suffix = str(i)
            room = max(1, MAX_USERNAME_LEN - len(suffix))
            candidate = f"{seed[:room]}{suffix}"

        existing_dn = svc.find_user_dn(conn, candidate)
        if not existing_dn:
            return candidate, False
        if _user_name_matches(conn, existing_dn, first_name=first_name, last_name=last_name):
            return candidate, True

    raise HTTPException(status_code=409, detail="cannot allocate available username")


def import_users_from_legacy_txt(
    files: Iterable[tuple[str, bytes]],
    default_group_cn: Optional[str] = "Students",
    password_length: int = DEFAULT_PASSWORD_LENGTH,
) -> UserImportResponse:
    file_list = list(files)
    if not file_list:
        raise HTTPException(status_code=400, detail="at least one file is required")

    group_cn = _normalize_spaces(default_group_cn or "") or None
    svc = get_ldap_service()

    results: list[UserImportItemResult] = []
    created = 0
    skipped = 0
    failed = 0
    total_lines = 0

    with svc.connection() as conn:
        group_dn = None
        if group_cn:
            group_dn = svc.find_group_dn(conn, group_cn)
            if not group_dn:
                raise HTTPException(status_code=400, detail=f"group not found: {group_cn}")

        for file_name, raw_bytes in file_list:
            try:
                text = _decode_legacy_text(raw_bytes)
                group_token = _extract_group_token(text)
                group_code, group_number = _parse_group_parts(group_token)
                ou_path = ["Students", group_code, group_number]
                parent_dn = svc.ensure_ou_path(conn, ou_path)
                name_lines = _extract_name_lines(text)
            except (ValueError, HTTPException, LDAPException) as err:
                failed += 1
                results.append(
                    UserImportItemResult(
                        file_name=file_name,
                        line_no=0,
                        raw_line="",
                        status="failed",
                        message=f"file parse failed: {err}",
                    )
                )
                continue

            for line_no, raw_line in name_lines:
                total_lines += 1
                try:
                    first_name, last_name = _split_person_name(raw_line)
                    seed = _build_legacy_username_seed(last_name=last_name, first_name=first_name)
                    username, already_exists = _resolve_import_username(
                        conn,
                        svc,
                        seed,
                        first_name=first_name,
                        last_name=last_name,
                    )

                    if already_exists:
                        skipped += 1
                        results.append(
                            UserImportItemResult(
                                file_name=file_name,
                                line_no=line_no,
                                raw_line=raw_line,
                                username=username,
                                first_name=first_name,
                                last_name=last_name,
                                ou_path=ou_path,
                                status="skipped",
                                message="user already exists with same generated username and name",
                            )
                        )
                        continue

                    password = _password(password_length)
                    user_dn = svc.create_user(
                        conn,
                        username,
                        password,
                        parent_dn=parent_dn,
                        first_name=first_name,
                        last_name=last_name,
                        display_name=f"{first_name} {last_name}".strip(),
                    )
                    if group_dn:
                        svc.add_user_to_group(conn, user_dn, group_dn)

                    created += 1
                    results.append(
                        UserImportItemResult(
                            file_name=file_name,
                            line_no=line_no,
                            raw_line=raw_line,
                            username=username,
                            password=password,
                            first_name=first_name,
                            last_name=last_name,
                            ou_path=ou_path,
                            status="created",
                            message="created",
                        )
                    )
                except (ValueError, HTTPException, LDAPException) as err:
                    failed += 1
                    results.append(
                        UserImportItemResult(
                            file_name=file_name,
                            line_no=line_no,
                            raw_line=raw_line,
                            status="failed",
                            message=str(err),
                        )
                    )

    return UserImportResponse(
        total_files=len(file_list),
        total_lines=total_lines,
        created=created,
        skipped=skipped,
        failed=failed,
        results=results,
    )


def _normalize_dn(dn: str) -> str:
    return ",".join(part.strip().lower() for part in str(dn or "").split(",") if part.strip())


def _extract_ou_path(dn: str) -> str:
    ous: list[str] = []
    for part in str(dn or "").split(","):
        p = part.strip()
        if p.upper().startswith("OU="):
            ous.append(p[3:])
    return " > ".join(reversed(ous))


def _parent_dn(dn: str) -> str:
    raw = str(dn or "")
    idx = raw.find(",")
    if idx < 0:
        return ""
    return raw[idx + 1 :]


def export_users_csv(
    keyword: str | None = None,
    ou_dn: str | None = None,
    group_cns: Optional[Iterable[str]] = None,
) -> bytes:
    svc = get_ldap_service()
    users = svc.list_users()
    groups = svc.list_groups()

    groups_by_user: dict[str, set[str]] = {}
    for group in groups:
        cn = (group.cn or "").strip()
        if not cn:
            continue
        for member_dn in group.members or []:
            key = _normalize_dn(member_dn)
            if not key:
                continue
            groups_by_user.setdefault(key, set()).add(cn)

    filtered_users = users
    target_ou = _normalize_dn(ou_dn or "")
    if target_ou:
        filtered_users = [
            user
            for user in filtered_users
            if _normalize_dn(_parent_dn(user.dn or "")) == target_ou
        ]

    normalized_group_cns = {
        _normalize_spaces(cn).lower()
        for cn in (group_cns or [])
        if _normalize_spaces(cn)
    }
    if normalized_group_cns:
        next_users: list = []
        for user in filtered_users:
            user_dn_key = _normalize_dn(user.dn or "")
            user_groups = groups_by_user.get(user_dn_key, set())
            if any((group or "").strip().lower() in normalized_group_cns for group in user_groups):
                next_users.append(user)
        filtered_users = next_users

    kw = _normalize_spaces(keyword or "").lower()
    if kw:
        next_users = []
        for user in filtered_users:
            dn = user.dn or ""
            dn_key = _normalize_dn(dn)
            user_groups = sorted(groups_by_user.get(dn_key, set()))
            fields = [
                user.sAMAccountName or "",
                user.givenName or "",
                user.sn or "",
                user.displayName or "",
                user.employeeID or "",
                user.employeeType or "",
                user.userPrincipalName or "",
                dn,
                _extract_ou_path(dn),
                " ".join(user_groups),
            ]
            if any(kw in field.lower() for field in fields):
                next_users.append(user)
        filtered_users = next_users

    ordered_users = sorted(
        filtered_users,
        key=lambda u: ((u.sAMAccountName or "").lower(), (u.displayName or "").lower(), (u.dn or "").lower()),
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "username",
            "first_name",
            "last_name",
            "display_name",
            "student_id",
            "paid_flag",
            "upn",
            "ou_path",
            "groups",
            "dn",
        ]
    )

    for user in ordered_users:
        dn = user.dn or ""
        dn_key = _normalize_dn(dn)
        user_groups = sorted(groups_by_user.get(dn_key, set()))
        writer.writerow(
            [
                user.sAMAccountName or "",
                user.givenName or "",
                user.sn or "",
                user.displayName or "",
                user.employeeID or "",
                user.employeeType or "",
                user.userPrincipalName or "",
                _extract_ou_path(dn),
                " | ".join(user_groups),
                dn,
            ]
        )

    # UTF-8 BOM for better spreadsheet compatibility.
    return output.getvalue().encode("utf-8-sig")
