# backend/app/services/ldap_service.py
from __future__ import annotations

import ssl
from contextlib import contextmanager
import re
import time
from typing import Dict, Iterator, List, Optional, Set

import ldap3
from ldap3.core.exceptions import LDAPException

from app.core.settings import LdapSettings
from app.schemas.ldap import GroupTreeNode, LdapGroup, LdapUser, OuTreeNode


class LdapService:
    def __init__(self, cfg: LdapSettings):
        self.cfg = cfg

    def _make_tls(self) -> ldap3.Tls:
        if getattr(self.cfg, "tls_skip_verify", True):
            return ldap3.Tls(validate=ssl.CERT_NONE)
        return ldap3.Tls(validate=ssl.CERT_REQUIRED)

    def _connect(self) -> ldap3.Connection:
        tls = self._make_tls() if (self.cfg.use_ssl or self.cfg.start_tls) else None

        server = ldap3.Server(
            self.cfg.host,
            port=self.cfg.port,
            use_ssl=self.cfg.use_ssl,
            tls=tls,
            get_info=ldap3.NONE,
        )

        conn = ldap3.Connection(
            server,
            user=self.cfg.bind_user,
            password=self.cfg.bind_password,
            auto_bind=False,
        )
        try:
            conn.open()
        except Exception as exc:
            raise LDAPException(
                "socket connection failed while opening "
                f"{self.cfg.host}:{self.cfg.port} "
                f"(use_ssl={self.cfg.use_ssl}, start_tls={self.cfg.start_tls}): {exc}"
            ) from exc

        if self.cfg.start_tls and not self.cfg.use_ssl:
            if not conn.start_tls():
                raise LDAPException(f"start_tls failed: {conn.result}")

        if not conn.bind():
            raise LDAPException(f"bind failed: {conn.result}")

        return conn

    @contextmanager
    def connection(self) -> Iterator[ldap3.Connection]:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.unbind()

    @staticmethod
    def _entry_attr(entry: object, attr: str) -> Optional[str]:
        if not hasattr(entry, attr):
            return None
        value = str(getattr(entry, attr, ""))
        if not value or value == "[]":
            return None
        return value

    @staticmethod
    def _escape_filter(value: str) -> str:
        return ldap3.utils.conv.escape_filter_chars(value)

    @staticmethod
    def _normalize_dn(value: str) -> str:
        return ",".join(part.strip().lower() for part in str(value or "").split(",") if part.strip())

    @staticmethod
    def _entry_attr_dict(entry: object) -> Dict[str, object]:
        raw = getattr(entry, "entry_attributes_as_dict", None)
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _entry_attr_values_by_key(entry: object, key: str) -> List[str]:
        values = LdapService._entry_attr_dict(entry).get(key, [])
        if values is None:
            return []
        if isinstance(values, list):
            return [str(v) for v in values if str(v)]
        return [str(values)] if str(values) else []

    @staticmethod
    def _find_range_attr_key(entry: object, attr_name: str) -> Optional[str]:
        prefix = f"{attr_name};range="
        for key in LdapService._entry_attr_dict(entry).keys():
            if str(key).lower().startswith(prefix):
                return str(key)
        return None

    def _read_member_values(self, conn: ldap3.Connection, entry: object) -> List[str]:
        # AD can return member values as ranged attributes: member;range=0-1499
        range_key = self._find_range_attr_key(entry, "member")
        if range_key:
            group_dn = self._entry_attr(entry, "distinguishedName") or ""
            if group_dn:
                return self._read_all_group_members_by_range(conn, group_dn)
            return self._entry_attr_values_by_key(entry, range_key)

        if hasattr(entry, "member"):
            return [str(x) for x in getattr(entry, "member", []) if str(x)]
        return []

    def _read_all_group_members_by_range(self, conn: ldap3.Connection, group_dn: str) -> List[str]:
        """
        Read all group members from AD using ranged member retrieval.
        Reference format: member;range=<start>-<end|*>
        """
        members: List[str] = []
        seen: Set[str] = set()
        start = 0
        range_re = re.compile(r"(?i)^member;range=(\d+)-(\d+|\*)$")

        while True:
            attr = f"member;range={start}-*"
            ok = conn.search(
                search_base=group_dn,
                search_filter="(objectClass=*)",
                search_scope=ldap3.BASE,
                attributes=[attr],
            )
            if not ok or not conn.entries:
                raise LDAPException(f"read group members failed: {conn.result}")

            entry = conn.entries[0]
            range_key = self._find_range_attr_key(entry, "member")
            if not range_key:
                # Some servers may return full member directly.
                chunk = self._entry_attr_values_by_key(entry, "member")
                for value in chunk:
                    if value in seen:
                        continue
                    seen.add(value)
                    if value:
                        members.append(value)
                break

            chunk = self._entry_attr_values_by_key(entry, range_key)
            for value in chunk:
                if value in seen:
                    continue
                seen.add(value)
                if value:
                    members.append(value)

            m = range_re.match(range_key)
            if not m:
                raise LDAPException(f"unexpected ranged member attribute key: {range_key}")
            end_token = m.group(2)
            if end_token == "*":
                break
            start = int(end_token) + 1

        return members

    def build_user_group_map(self) -> Dict[str, List[str]]:
        groups = self.list_groups(include_members=True, include_description=False)
        out: Dict[str, Set[str]] = {}
        for group in groups:
            cn = (group.cn or "").strip()
            if not cn:
                continue
            for member_dn in group.members or []:
                key = self._normalize_dn(member_dn)
                if not key:
                    continue
                out.setdefault(key, set()).add(cn)

        result: Dict[str, List[str]] = {}
        for dn_key, values in out.items():
            result[dn_key] = sorted(values, key=lambda x: x.lower())
        return result

    def _domain_from_base_dn(self) -> str:
        if self.cfg.user_upn_suffix:
            return self.cfg.user_upn_suffix

        labels: List[str] = []
        for part in self.cfg.base_dn.split(","):
            p = part.strip()
            if p.lower().startswith("dc="):
                labels.append(p[3:])
        return ".".join(labels)

    def _users_container_dn(self) -> str:
        if self.cfg.user_container_dn:
            return self.cfg.user_container_dn
        return f"CN=Users,{self.cfg.base_dn}"

    @staticmethod
    def _parent_dn(dn: str) -> str:
        raw = str(dn or "")
        idx = raw.find(",")
        if idx < 0:
            return ""
        return raw[idx + 1 :]

    @staticmethod
    def _extract_ou_path(dn: str) -> str:
        ous: List[str] = []
        for part in str(dn or "").split(","):
            p = part.strip()
            if p.upper().startswith("OU="):
                ous.append(p[3:])
        return " > ".join(reversed(ous))

    @staticmethod
    def _ancestor_dns(dn: str) -> List[str]:
        """
        Return normalized DN ancestor chain from current DN upward.
        Example: 'OU=b,OU=a,DC=x,DC=com' -> ['ou=b,ou=a,dc=x,dc=com', 'ou=a,dc=x,dc=com', 'dc=x,dc=com']
        """
        raw_parts = [part.strip() for part in str(dn or "").split(",") if part.strip()]
        out: List[str] = []
        for idx in range(len(raw_parts)):
            out.append(",".join(part.lower() for part in raw_parts[idx:]))
        return out

    @staticmethod
    def _parse_ldap_timestamp(value: Optional[str]) -> int:
        raw = str(value or "").strip()
        if not raw:
            return 0
        if raw.isdigit():
            n = int(raw)
            if n <= 0:
                return 0
            if n > 100000000000000:
                ms = n // 10000 - 11644473600000
                return ms if ms > 0 else 0
            if n > 1000000000000:
                return n
            if n > 1000000000:
                return n * 1000
            return 0

        m = re.match(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?:\.\d+)?Z$", raw, flags=re.I)
        if m:
            import calendar
            from datetime import datetime

            dt = datetime(
                year=int(m.group(1)),
                month=int(m.group(2)),
                day=int(m.group(3)),
                hour=int(m.group(4)),
                minute=int(m.group(5)),
                second=int(m.group(6)),
            )
            return calendar.timegm(dt.timetuple()) * 1000
        return 0

    def _search_entries_paged(
        self,
        conn: ldap3.Connection,
        *,
        search_base: str,
        search_filter: str,
        attributes: List[str],
        search_scope: int = ldap3.SUBTREE,
        paged_size: int = 500,
    ) -> List[object]:
        """
        Execute LDAP search with simple paged results control.
        This prevents silent truncation in directories with server-side size limits.
        """
        entries: List[object] = []
        cookie: object = None
        while True:
            ok = conn.search(
                search_base=search_base,
                search_filter=search_filter,
                search_scope=search_scope,
                attributes=attributes,
                paged_size=paged_size,
                paged_cookie=cookie,
            )
            if not ok:
                raise LDAPException(f"ldap search failed: {conn.result}")
            entries.extend(conn.entries)
            controls = conn.result.get("controls", {}) if isinstance(conn.result, dict) else {}
            page = controls.get("1.2.840.113556.1.4.319", {})
            value = page.get("value", {}) if isinstance(page, dict) else {}
            cookie = value.get("cookie") if isinstance(value, dict) else None
            if not cookie:
                break
        return entries

    @staticmethod
    def _user_attributes_for_view(view: str) -> List[str]:
        normalized = (view or "full").strip().lower()
        view_map: Dict[str, List[str]] = {
            "full": [
                "distinguishedName",
                "sAMAccountName",
                "displayName",
                "userPrincipalName",
                "givenName",
                "sn",
                "employeeID",
                "employeeType",
                "whenCreated",
                "whenChanged",
                "lastLogon",
                "lastLogoff",
            ],
            "list": [
                "distinguishedName",
                "sAMAccountName",
                "displayName",
                "userPrincipalName",
                "givenName",
                "sn",
                "employeeID",
                "employeeType",
                "whenCreated",
                "whenChanged",
            ],
            "dashboard": [
                "distinguishedName",
                "sAMAccountName",
                "displayName",
                "userPrincipalName",
                "givenName",
                "sn",
                "lastLogon",
                "lastLogoff",
            ],
            "tree": [
                "distinguishedName",
                "sAMAccountName",
                "displayName",
            ],
        }
        return view_map.get(normalized, view_map["full"])

    def _ldap_user_from_entry(self, entry: object) -> LdapUser:
        return LdapUser(
            dn=self._entry_attr(entry, "distinguishedName") or "",
            sAMAccountName=self._entry_attr(entry, "sAMAccountName"),
            displayName=self._entry_attr(entry, "displayName"),
            userPrincipalName=self._entry_attr(entry, "userPrincipalName"),
            givenName=self._entry_attr(entry, "givenName"),
            sn=self._entry_attr(entry, "sn"),
            employeeID=self._entry_attr(entry, "employeeID"),
            employeeType=self._entry_attr(entry, "employeeType"),
            whenCreated=self._entry_attr(entry, "whenCreated"),
            whenChanged=self._entry_attr(entry, "whenChanged"),
            lastLogon=self._entry_attr(entry, "lastLogon"),
            lastLogoff=self._entry_attr(entry, "lastLogoff"),
        )

    # ----------------------------
    # Generic LDAP operations (write/read)
    # ----------------------------

    def find_user_dn(self, conn: ldap3.Connection, username: str) -> Optional[str]:
        flt = f"(&(objectClass=user)(sAMAccountName={self._escape_filter(username)}))"
        ok = conn.search(
            search_base=self.cfg.base_dn,
            search_filter=flt,
            attributes=["distinguishedName"],
        )
        if not ok or not conn.entries:
            return None
        return self._entry_attr(conn.entries[0], "distinguishedName")

    def find_group_dn(self, conn: ldap3.Connection, group_cn: str) -> Optional[str]:
        flt = (
            f"(&(objectClass=group)(cn={self._escape_filter(group_cn)}))"
        )
        ok = conn.search(
            search_base=self.cfg.base_dn,
            search_filter=flt,
            attributes=["distinguishedName"],
        )
        if not ok or not conn.entries:
            return None
        return self._entry_attr(conn.entries[0], "distinguishedName")

    def _entry_exists_dn(self, conn: ldap3.Connection, dn: str) -> bool:
        ok = conn.search(
            search_base=dn,
            search_filter="(objectClass=*)",
            search_scope=ldap3.BASE,
            attributes=["distinguishedName"],
        )
        if ok and conn.entries:
            return True

        result_code = int(conn.result.get("result", -1)) if isinstance(conn.result, dict) else -1
        if result_code == 32:
            return False
        if result_code in (0,):
            return False
        raise LDAPException(f"dn lookup failed: {conn.result}")

    def ensure_ou_path(self, conn: ldap3.Connection, ou_path: List[str]) -> str:
        """
        Ensure nested OU exists under base DN.
        ou_path order: root -> leaf, e.g. ["Students", "ms", "101"].
        Return leaf DN (or base DN when path is empty).
        """
        parent_dn = self.cfg.base_dn
        for ou_name in ou_path:
            escaped = ldap3.utils.dn.escape_rdn(ou_name)
            ou_dn = f"OU={escaped},{parent_dn}"
            if not self._entry_exists_dn(conn, ou_dn):
                ok = conn.add(
                    ou_dn,
                    object_class=["top", "organizationalUnit"],
                    attributes={"ou": ou_name},
                )
                if not ok:
                    result_code = int(conn.result.get("result", -1)) if isinstance(conn.result, dict) else -1
                    if result_code != 68:  # entryAlreadyExists
                        raise LDAPException(f"create OU failed: {conn.result}")
            parent_dn = ou_dn
        return parent_dn

    def create_ou(self, conn: ldap3.Connection, name: str, parent_dn: Optional[str] = None) -> tuple[str, bool]:
        ou_name = name.strip()
        if not ou_name:
            raise LDAPException("ou name cannot be empty")

        target_parent_dn = parent_dn.strip() if parent_dn else self.cfg.base_dn
        if not self._entry_exists_dn(conn, target_parent_dn):
            raise LDAPException(f"parent DN not found: {target_parent_dn}")

        ou_dn = f"OU={ldap3.utils.dn.escape_rdn(ou_name)},{target_parent_dn}"
        if self._entry_exists_dn(conn, ou_dn):
            return ou_dn, False

        ok = conn.add(
            ou_dn,
            object_class=["top", "organizationalUnit"],
            attributes={"ou": ou_name},
        )
        if not ok:
            result_code = int(conn.result.get("result", -1)) if isinstance(conn.result, dict) else -1
            if result_code == 68:  # entryAlreadyExists
                return ou_dn, False
            raise LDAPException(f"create OU failed: {conn.result}")

        return ou_dn, True

    def rename_ou(self, conn: ldap3.Connection, ou_dn: str, new_name: str) -> str:
        source_dn = ou_dn.strip()
        target_name = new_name.strip()
        if not source_dn:
            raise LDAPException("ou DN cannot be empty")
        if not target_name:
            raise LDAPException("new OU name cannot be empty")
        if source_dn.lower() == self.cfg.base_dn.lower():
            raise LDAPException("cannot rename base DN")

        ok = conn.search(
            search_base=source_dn,
            search_filter="(objectClass=*)",
            search_scope=ldap3.BASE,
            attributes=["objectClass", "distinguishedName"],
        )
        if not ok or not conn.entries:
            raise LDAPException(f"OU not found: {source_dn}")

        classes = self._entry_object_classes(conn.entries[0])
        if "organizationalunit" not in classes:
            raise LDAPException(f"target is not an OU: {source_dn}")

        parts = source_dn.split(",", 1)
        if len(parts) != 2:
            raise LDAPException(f"invalid OU DN: {source_dn}")
        parent_dn = parts[1]
        new_rdn = f"OU={ldap3.utils.dn.escape_rdn(target_name)}"
        target_dn = f"{new_rdn},{parent_dn}"

        if source_dn.lower() == target_dn.lower():
            return source_dn

        if self._entry_exists_dn(conn, target_dn):
            raise LDAPException(f"target DN already exists: {target_dn}")

        ok = conn.modify_dn(
            dn=source_dn,
            relative_dn=new_rdn,
            delete_old_dn=True,
        )
        if not ok:
            result_code = int(conn.result.get("result", -1)) if isinstance(conn.result, dict) else -1
            if result_code == 68:
                raise LDAPException(f"target DN already exists: {target_dn}")
            if result_code == 50:
                raise LDAPException(f"insufficient access rights to rename OU: {source_dn}")
            raise LDAPException(f"rename OU failed: {conn.result}")

        # AD updates descendants DNs automatically on parent rename/move.
        return target_dn

    def _entry_object_classes(self, entry: object) -> Set[str]:
        raw = getattr(entry, "objectClass", []) if hasattr(entry, "objectClass") else []
        return {str(x).lower() for x in raw}

    def delete_ou(self, conn: ldap3.Connection, ou_dn: str, recursive: bool = False) -> int:
        dn = ou_dn.strip()
        if not dn:
            raise LDAPException("ou DN cannot be empty")
        if dn.lower() == self.cfg.base_dn.lower():
            raise LDAPException("cannot delete base DN")

        ok = conn.search(
            search_base=dn,
            search_filter="(objectClass=*)",
            search_scope=ldap3.BASE,
            attributes=["objectClass", "distinguishedName"],
        )
        if not ok or not conn.entries:
            raise LDAPException(f"OU not found: {dn}")

        classes = self._entry_object_classes(conn.entries[0])
        if "organizationalunit" not in classes:
            raise LDAPException(f"target is not an OU: {dn}")

        ok = conn.search(
            search_base=dn,
            search_filter="(objectClass=*)",
            search_scope=ldap3.LEVEL,
            attributes=["distinguishedName"],
        )
        children_dns = [str(getattr(e, "distinguishedName", "")) for e in conn.entries if str(getattr(e, "distinguishedName", ""))]
        if children_dns and not recursive:
            raise LDAPException("OU is not empty; recursive delete required")

        if not recursive:
            if not conn.delete(dn):
                raise LDAPException(f"delete OU failed: {conn.result}")
            return 1

        # Subtree delete (leaf-first): fetch all descendants + root and delete by depth.
        ok = conn.search(
            search_base=dn,
            search_filter="(objectClass=*)",
            search_scope=ldap3.SUBTREE,
            attributes=["distinguishedName"],
        )
        if not ok:
            raise LDAPException(f"read OU subtree failed: {conn.result}")

        dns = [str(getattr(e, "distinguishedName", "")) for e in conn.entries if str(getattr(e, "distinguishedName", ""))]
        ordered_dns = sorted(set(dns), key=lambda x: x.count(","), reverse=True)

        deleted = 0
        for child_dn in ordered_dns:
            if not conn.delete(child_dn):
                result_code = int(conn.result.get("result", -1)) if isinstance(conn.result, dict) else -1
                if result_code == 32:
                    continue
                raise LDAPException(f"delete subtree entry failed: {child_dn} => {conn.result}")
            deleted += 1

        return deleted

    def create_user(
        self,
        conn: ldap3.Connection,
        username: str,
        password: str,
        parent_dn: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> str:
        target_parent_dn = parent_dn or self._users_container_dn()
        user_dn = f"CN={ldap3.utils.dn.escape_rdn(username)},{target_parent_dn}"
        user_principal_name = f"{username}@{self._domain_from_base_dn()}"
        safe_first = (first_name or "").strip()
        safe_last = (last_name or "").strip()
        resolved_display_name = (display_name or "").strip() or f"{safe_first} {safe_last}".strip()

        attributes = {
            "objectClass": ["top", "person", "organizationalPerson", "user"],
            "cn": username,
            "sn": safe_last or username,
            "sAMAccountName": username,
            "userPrincipalName": user_principal_name,
            # 514: normal account + disabled
            "userAccountControl": "514",
        }
        if safe_first:
            attributes["givenName"] = safe_first
        if resolved_display_name:
            attributes["displayName"] = resolved_display_name

        if not conn.add(user_dn, attributes=attributes):
            raise LDAPException(f"create user failed: {conn.result}")

        self.set_user_password(conn, user_dn, password)

        # 512: normal account + enabled
        if not conn.modify(user_dn, {"userAccountControl": [(ldap3.MODIFY_REPLACE, ["512"])]}):
            raise LDAPException(f"enable user failed: {conn.result}")

        return user_dn

    def move_user_to_parent(self, conn: ldap3.Connection, user_dn: str, username: str, parent_dn: str) -> str:
        new_rdn = f"CN={ldap3.utils.dn.escape_rdn(username)}"
        target_dn = f"{new_rdn},{parent_dn}"
        if user_dn.lower() == target_dn.lower():
            return user_dn

        # Pre-check to return clear conflict errors before modify_dn.
        if self._entry_exists_dn(conn, target_dn):
            raise LDAPException(f"target DN already exists: {target_dn}")

        ok = conn.modify_dn(
            dn=user_dn,
            relative_dn=new_rdn,
            delete_old_dn=True,
            new_superior=parent_dn,
        )
        if not ok:
            result_code = int(conn.result.get("result", -1)) if isinstance(conn.result, dict) else -1
            if result_code == 68:
                raise LDAPException(f"target DN already exists: {target_dn}")
            if result_code == 50:
                raise LDAPException(f"insufficient access rights to move user: {user_dn}")
            raise LDAPException(f"move user failed: {conn.result}")

        return target_dn

    def set_user_password(self, conn: ldap3.Connection, user_dn: str, password: str) -> None:
        ok = conn.extend.microsoft.modify_password(user=user_dn, new_password=password)
        if not ok:
            raise LDAPException(f"set password failed: {conn.result}")

    def delete_user(self, conn: ldap3.Connection, user_dn: str) -> None:
        if not conn.delete(user_dn):
            raise LDAPException(f"delete user failed: {conn.result}")

    def update_user_profile(
        self,
        conn: ldap3.Connection,
        user_dn: str,
        student_id: Optional[str],
        first_name: str,
        last_name: str,
        display_name: Optional[str],
        paid_flag: Optional[str],
    ) -> List[str]:
        resolved_display_name = (display_name or "").strip() or f"{first_name} {last_name}".strip()
        base_changes: Dict[str, List[tuple[int, List[str]]]] = {
            "displayName": [(ldap3.MODIFY_REPLACE, [resolved_display_name])],
            "givenName": [(ldap3.MODIFY_REPLACE, [first_name])],
            "sn": [(ldap3.MODIFY_REPLACE, [last_name])],
        }

        safe_student_id = (student_id or "").strip()
        if safe_student_id:
            base_changes["employeeID"] = [(ldap3.MODIFY_REPLACE, [safe_student_id])]

        if not conn.modify(user_dn, base_changes):
            raise LDAPException(f"update user attributes failed: {conn.result}")

        updated: List[str] = ["displayName", "givenName", "sn"]
        if safe_student_id:
            updated.append("employeeID")

        if paid_flag == "$":
            if not conn.modify(user_dn, {"employeeType": [(ldap3.MODIFY_REPLACE, ["$"])]}):
                raise LDAPException(f"update user attributes failed: {conn.result}")
            updated.append("employeeType")
        elif paid_flag is None:
            if not conn.modify(user_dn, {"employeeType": [(ldap3.MODIFY_DELETE, [])]}):
                result_code = int(conn.result.get("result", -1)) if isinstance(conn.result, dict) else -1
                # noSuchAttribute: employeeType absent is acceptable when clearing paid flag
                if result_code != 16:
                    raise LDAPException(f"update user attributes failed: {conn.result}")
            updated.append("employeeType")

        return updated

    def update_user_login_identifiers(self, conn: ldap3.Connection, user_dn: str, username: str) -> List[str]:
        user_principal_name = f"{username}@{self._domain_from_base_dn()}"
        changes: Dict[str, List[tuple[int, List[str]]]] = {
            "sAMAccountName": [(ldap3.MODIFY_REPLACE, [username])],
            "userPrincipalName": [(ldap3.MODIFY_REPLACE, [user_principal_name])],
        }
        if not conn.modify(user_dn, changes):
            raise LDAPException(f"update user login attributes failed: {conn.result}")
        return ["sAMAccountName", "userPrincipalName"]

    def add_user_to_group(self, conn: ldap3.Connection, user_dn: str, group_dn: str) -> None:
        ok = conn.modify(group_dn, {"member": [(ldap3.MODIFY_ADD, [user_dn])]})
        if ok:
            return

        # typeOrValueExists => already member
        result_code = int(conn.result.get("result", -1)) if isinstance(conn.result, dict) else -1
        if result_code == 20:
            return

        message = str(conn.result).lower()
        if "already" in message and "member" in message:
            return

        raise LDAPException(f"add group membership failed: {conn.result}")

    def remove_user_from_group(self, conn: ldap3.Connection, user_dn: str, group_dn: str) -> None:
        ok = conn.modify(group_dn, {"member": [(ldap3.MODIFY_DELETE, [user_dn])]})
        if ok:
            return

        result_code = int(conn.result.get("result", -1)) if isinstance(conn.result, dict) else -1
        # noSuchAttribute => already not a member
        if result_code == 16:
            return

        message = str(conn.result).lower()
        if "not" in message and "member" in message:
            return

        raise LDAPException(f"remove group membership failed: {conn.result}")

    def list_user_groups(self, conn: ldap3.Connection, user_dn: str) -> List[LdapGroup]:
        flt = f"(&(objectClass=group)(member={self._escape_filter(user_dn)}))"
        entries = self._search_entries_paged(
            conn,
            search_base=self.cfg.base_dn,
            search_filter=flt,
            attributes=["cn", "distinguishedName"],
        )

        groups: List[LdapGroup] = []
        for e in entries:
            groups.append(
                LdapGroup(
                    cn=str(getattr(e, "cn", "")),
                    dn=str(getattr(e, "distinguishedName", "")),
                    description=None,
                    members=[],
                )
            )
        return groups

    # ----------------------------
    # Health / Groups / Users
    # ----------------------------

    def ping(self) -> None:
        with self.connection() as conn:
            conn.search(
                search_base=self.cfg.base_dn,
                search_filter="(objectClass=*)",
                search_scope=ldap3.BASE,
                attributes=["defaultNamingContext"],
            )

    def list_groups(self, include_members: bool = True, include_description: bool = True) -> List[LdapGroup]:
        attrs = ["cn", "distinguishedName"]
        if include_members:
            attrs.append("member")
        if include_description:
            attrs.append("description")

        with self.connection() as conn:
            entries = self._search_entries_paged(
                conn,
                search_base=self.cfg.base_dn,
                search_filter="(objectClass=group)",
                attributes=attrs,
            )
            groups: List[LdapGroup] = []
            for e in entries:
                groups.append(
                    LdapGroup(
                        cn=str(getattr(e, "cn", "")),
                        dn=str(getattr(e, "distinguishedName", "")),
                        description=(
                            str(getattr(e, "description", "")) if include_description and hasattr(e, "description") else None
                        ),
                        members=(self._read_member_values(conn, e) if include_members else []),
                    )
                )
            return groups

    def list_users(self, view: str = "full") -> List[LdapUser]:
        attrs = self._user_attributes_for_view(view)
        with self.connection() as conn:
            entries = self._search_entries_paged(
                conn,
                search_base=self.cfg.base_dn,
                search_filter="(&(objectClass=user)(!(objectClass=computer)))",
                attributes=attrs,
            )
            users: List[LdapUser] = []
            for e in entries:
                users.append(self._ldap_user_from_entry(e))
            return users

    def dashboard_summary(self, *, recent_window_days: int = 3) -> Dict[str, int]:
        users = self.list_users(view="dashboard")
        total_users = len(users)
        now_ms = int(time.time() * 1000)
        window_ms = max(1, int(recent_window_days)) * 24 * 60 * 60 * 1000
        threshold = now_ms - window_ms
        recent_login_users = 0
        for user in users:
            login_ts = self._parse_ldap_timestamp(user.lastLogon)
            if login_ts >= threshold:
                recent_login_users += 1
        return {
            "total_users": total_users,
            "recent_login_users": recent_login_users,
        }

    def list_users_page(
        self,
        *,
        view: str = "list",
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        ou_dn: Optional[str] = None,
        ou_dns: Optional[List[str]] = None,
        ou_scope: str = "direct",
        group_cns: Optional[List[str]] = None,
        login_from_ms: Optional[int] = None,
        login_to_ms: Optional[int] = None,
    ) -> Dict[str, object]:
        safe_page = max(1, int(page))
        safe_page_size = max(1, min(int(page_size), 200))
        users = self.list_users(view=view)

        target_ous: List[str] = []
        for raw in ([ou_dn] if ou_dn is not None else []) + list(ou_dns or []):
            normalized = self._normalize_dn(raw or "")
            if normalized and normalized not in target_ous:
                target_ous.append(normalized)

        if target_ous:
            use_subtree = str(ou_scope or "").strip().lower() == "subtree"
            if use_subtree:
                users = [
                    u
                    for u in users
                    if (
                        lambda ancestors: any(target_ou in ancestors for target_ou in target_ous)
                    )(set(self._ancestor_dns(self._parent_dn(u.dn or ""))))
                ]
            else:
                users = [u for u in users if self._normalize_dn(self._parent_dn(u.dn or "")) in target_ous]

        selected_groups = [str(x or "").strip() for x in (group_cns or []) if str(x or "").strip()]
        if selected_groups:
            member_dns: Set[str] = set()
            with self.connection() as conn:
                for group_cn in selected_groups:
                    group_dn = self.find_group_dn(conn, group_cn)
                    if not group_dn:
                        continue
                    ok = conn.search(
                        search_base=group_dn,
                        search_filter="(objectClass=*)",
                        search_scope=ldap3.BASE,
                        attributes=["member"],
                    )
                    if not ok or not conn.entries:
                        continue
                    members = self._read_member_values(conn, conn.entries[0])
                    for member_dn in members:
                        key = self._normalize_dn(member_dn)
                        if key:
                            member_dns.add(key)
            if member_dns:
                users = [u for u in users if self._normalize_dn(u.dn or "") in member_dns]
            else:
                users = []

        min_login = int(login_from_ms or 0)
        max_login = int(login_to_ms or 0)
        if min_login and max_login and min_login > max_login:
            min_login, max_login = max_login, min_login
        if min_login or max_login:
            upper = max_login if max_login > 0 else 2**63 - 1
            users = [
                u
                for u in users
                if (lambda ts: ts >= min_login and ts <= upper)(self._parse_ldap_timestamp(u.lastLogon))
            ]

        kw = str(keyword or "").strip().lower()
        if kw:
            filtered: List[LdapUser] = []
            for u in users:
                dn = u.dn or ""
                fields = [
                    u.sAMAccountName or "",
                    u.displayName or "",
                    u.userPrincipalName or "",
                    u.givenName or "",
                    u.sn or "",
                    u.employeeID or "",
                    u.employeeType or "",
                    dn,
                    self._extract_ou_path(dn),
                    u.whenCreated or "",
                    u.whenChanged or "",
                    u.lastLogon or "",
                    u.lastLogoff or "",
                ]
                if any(kw in f.lower() for f in fields):
                    filtered.append(u)
            users = filtered

        # Default user list order: most recently changed/created first.
        # When timestamps are equal or missing, fall back to stable lexical keys.
        users.sort(
            key=lambda u: (
                -max(
                    self._parse_ldap_timestamp(u.whenChanged),
                    self._parse_ldap_timestamp(u.whenCreated),
                ),
                (u.sAMAccountName or "").lower(),
                (u.displayName or "").lower(),
                (u.dn or "").lower(),
            )
        )
        total = len(users)
        start = (safe_page - 1) * safe_page_size
        page_users = users[start : start + safe_page_size]

        items: List[Dict[str, object]] = []
        with self.connection() as conn:
            for u in page_users:
                user_dn = str(u.dn or "").strip()
                memberships = self.list_user_groups(conn, user_dn) if user_dn else []
                groups = sorted([str(g.cn or "").strip() for g in memberships if str(g.cn or "").strip()], key=lambda x: x.lower())
                user_data = u.model_dump()
                user_data["groups"] = groups
                items.append(user_data)

        return {
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "items": items,
        }

    def build_ou_tree(self, include_users: bool = True, user_view: str = "full") -> List[OuTreeNode]:
        with self.connection() as conn:
            ou_entries = self._search_entries_paged(
                conn,
                search_base=self.cfg.base_dn,
                search_filter="(objectClass=organizationalUnit)",
                attributes=["distinguishedName", "ou"],
            )

            user_entries: List[object] = []
            if include_users:
                user_entries = self._search_entries_paged(
                    conn,
                    search_base=self.cfg.base_dn,
                    search_filter="(&(objectClass=user)(!(objectClass=computer)))",
                    attributes=self._user_attributes_for_view(user_view),
                )

        dn_to_node: Dict[str, OuTreeNode] = {}
        children_by_parent: Dict[str, Set[str]] = {}
        base_dn_lower = self.cfg.base_dn.lower()

        for entry in ou_entries:
            dn = str(getattr(entry, "distinguishedName", ""))
            if not dn:
                continue
            ou = str(getattr(entry, "ou", "")) if hasattr(entry, "ou") else ""
            if not ou and dn.upper().startswith("OU="):
                ou = dn.split("=", 1)[1].split(",", 1)[0]

            key = dn.lower()
            dn_to_node[key] = OuTreeNode(dn=dn, ou=ou or dn, users=[], children=[])

            parts = dn.split(",", 1)
            parent_dn = parts[1] if len(parts) == 2 else ""
            parent_key = parent_dn.lower()
            children_by_parent.setdefault(parent_key, set()).add(key)

        for entry in user_entries:
            user_dn = str(getattr(entry, "distinguishedName", ""))
            if not user_dn:
                continue
            parts = user_dn.split(",", 1)
            if len(parts) != 2:
                continue
            parent_key = parts[1].lower()
            parent = dn_to_node.get(parent_key)
            if not parent:
                continue
            parent.users.append(self._ldap_user_from_entry(entry))

        for node in dn_to_node.values():
            node.users.sort(key=lambda u: (u.sAMAccountName or "").lower())

        root_keys: List[str] = []
        for key, node in dn_to_node.items():
            parts = node.dn.split(",", 1)
            parent_dn = parts[1] if len(parts) == 2 else ""
            parent_key = parent_dn.lower()
            if parent_key == base_dn_lower or parent_key not in dn_to_node:
                root_keys.append(key)
        root_keys.sort(key=lambda k: (dn_to_node[k].ou or "").lower())

        def build_node(key: str, visited: Set[str]) -> OuTreeNode:
            src = dn_to_node[key]
            if key in visited:
                return OuTreeNode(dn=src.dn, ou=src.ou, users=src.users, children=[])

            next_visited = set(visited)
            next_visited.add(key)
            children: List[OuTreeNode] = []
            for child_key in sorted(children_by_parent.get(key, set()), key=lambda k: (dn_to_node[k].ou or "").lower()):
                if child_key in dn_to_node:
                    children.append(build_node(child_key, next_visited))

            return OuTreeNode(dn=src.dn, ou=src.ou, users=src.users, children=children)

        return [build_node(k, set()) for k in root_keys]

    # ----------------------------
    # Group Tree (nested groups + users)
    # ----------------------------

    def _fetch_users_by_dn(self, dns: List[str]) -> Dict[str, LdapUser]:
        """
        Batch-fetch user information by DN.
        Note: LDAP filters have length limits, so query in batches for large DN sets.
        """
        with self.connection() as conn:
            out: Dict[str, LdapUser] = {}
            batch_size = 20
            for i in range(0, len(dns), batch_size):
                batch = dns[i : i + batch_size]
                or_filter = "(|" + "".join([f"(distinguishedName={self._escape_filter(dn)})" for dn in batch]) + ")"
                flt = f"(&{or_filter}(objectClass=user)(!(objectClass=computer)))"
                conn.search(
                    search_base=self.cfg.base_dn,
                    search_filter=flt,
                    attributes=[
                        "distinguishedName",
                        "sAMAccountName",
                        "displayName",
                        "userPrincipalName",
                        "givenName",
                        "sn",
                        "whenCreated",
                        "whenChanged",
                        "lastLogon",
                        "lastLogoff",
                    ],
                )
                for e in conn.entries:
                    dn = str(getattr(e, "distinguishedName", ""))
                    key = self._normalize_dn(dn)
                    if not key:
                        continue
                    out[key] = LdapUser(
                        dn=dn,
                        sAMAccountName=str(getattr(e, "sAMAccountName", "")) if hasattr(e, "sAMAccountName") else None,
                        displayName=str(getattr(e, "displayName", "")) if hasattr(e, "displayName") else None,
                        userPrincipalName=str(getattr(e, "userPrincipalName", "")) if hasattr(e, "userPrincipalName") else None,
                        givenName=str(getattr(e, "givenName", "")) if hasattr(e, "givenName") else None,
                        sn=str(getattr(e, "sn", "")) if hasattr(e, "sn") else None,
                        whenCreated=str(getattr(e, "whenCreated", "")) if hasattr(e, "whenCreated") else None,
                        whenChanged=str(getattr(e, "whenChanged", "")) if hasattr(e, "whenChanged") else None,
                        lastLogon=str(getattr(e, "lastLogon", "")) if hasattr(e, "lastLogon") else None,
                        lastLogoff=str(getattr(e, "lastLogoff", "")) if hasattr(e, "lastLogoff") else None,
                    )
            return out

    def build_group_tree(self, root_group_cn: Optional[str] = None) -> List[GroupTreeNode]:
        """
        Build a tree based on nested group memberships.
        """
        groups = self.list_groups()
        dn_to_group: Dict[str, LdapGroup] = {}
        for g in groups:
            key = self._normalize_dn(g.dn)
            if key:
                dn_to_group[key] = g

        child_groups: Dict[str, Set[str]] = {key: set() for key in dn_to_group}
        # parent-group-key -> { normalized_user_dn: original_user_dn }
        group_users: Dict[str, Dict[str, str]] = {key: {} for key in dn_to_group}

        for g in groups:
            parent_key = self._normalize_dn(g.dn)
            if not parent_key:
                continue
            for member_dn in (g.members or []):
                member_key = self._normalize_dn(member_dn)
                if not member_key:
                    continue
                if member_key in dn_to_group:
                    child_groups[parent_key].add(member_key)
                else:
                    group_users[parent_key][member_key] = member_dn

        roots: List[str] = []
        if root_group_cn:
            for g in groups:
                if (g.cn or "").strip().lower() == root_group_cn.strip().lower():
                    key = self._normalize_dn(g.dn)
                    if key:
                        roots = [key]
                    break
            if not roots:
                return []
        else:
            referenced: Set[str] = set()
            for kids in child_groups.values():
                referenced |= set(kids)
            for key in sorted(dn_to_group.keys(), key=lambda k: (dn_to_group[k].cn or "").lower()):
                if key not in referenced:
                    roots.append(key)

        all_user_dns: List[str] = sorted({dn for user_map in group_users.values() for dn in user_map.values()})
        dn_to_user = self._fetch_users_by_dn(all_user_dns) if all_user_dns else {}

        def build_node(group_dn: str, visited: Set[str]) -> GroupTreeNode:
            g = dn_to_group.get(group_dn)
            node_dn = g.dn if g and g.dn else group_dn
            node_cn = g.cn if g and g.cn else group_dn

            if group_dn in visited:
                return GroupTreeNode(dn=node_dn, cn=node_cn, users=[], groups=[])

            next_visited = set(visited)
            next_visited.add(group_dn)

            users: List[LdapUser] = []
            for u_dn_key in sorted(group_users.get(group_dn, {}).keys()):
                u = dn_to_user.get(u_dn_key)
                if u:
                    users.append(u)

            sub_nodes: List[GroupTreeNode] = []
            for child_dn in sorted(child_groups.get(group_dn, set())):
                sub_nodes.append(build_node(child_dn, next_visited))

            return GroupTreeNode(dn=node_dn, cn=node_cn, users=users, groups=sub_nodes)

        return [build_node(r, set()) for r in roots]
