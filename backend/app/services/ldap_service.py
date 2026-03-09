# backend/app/services/ldap_service.py
from __future__ import annotations

import ssl
from contextlib import contextmanager
from typing import Dict, Iterator, List, Optional, Set

import ldap3
from ldap3.core.exceptions import LDAPException

from app.core.settings import LdapSettings
from app.models.schema import GroupTreeNode, LdapGroup, LdapUser


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
        conn.open()

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
        return value if value else None

    @staticmethod
    def _escape_filter(value: str) -> str:
        return ldap3.utils.conv.escape_filter_chars(value)

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

    def create_user(self, conn: ldap3.Connection, username: str, password: str) -> str:
        user_dn = f"CN={username},{self._users_container_dn()}"
        user_principal_name = f"{username}@{self._domain_from_base_dn()}"

        attributes = {
            "objectClass": ["top", "person", "organizationalPerson", "user"],
            "cn": username,
            "sn": username,
            "sAMAccountName": username,
            "userPrincipalName": user_principal_name,
            # 514: normal account + disabled
            "userAccountControl": "514",
        }

        if not conn.add(user_dn, attributes=attributes):
            raise LDAPException(f"create user failed: {conn.result}")

        self.set_user_password(conn, user_dn, password)

        # 512: normal account + enabled
        if not conn.modify(user_dn, {"userAccountControl": [(ldap3.MODIFY_REPLACE, ["512"])]}):
            raise LDAPException(f"enable user failed: {conn.result}")

        return user_dn

    def set_user_password(self, conn: ldap3.Connection, user_dn: str, password: str) -> None:
        ok = conn.extend.microsoft.modify_password(user=user_dn, new_password=password)
        if not ok:
            raise LDAPException(f"set password failed: {conn.result}")

    def update_user_profile(
        self,
        conn: ldap3.Connection,
        user_dn: str,
        student_id: str,
        russian_name: str,
        pinyin_name: str,
        paid_flag: Optional[str],
    ) -> List[str]:
        changes: Dict[str, List[tuple[int, List[str]]]] = {
            "displayName": [(ldap3.MODIFY_REPLACE, [russian_name])],
            "givenName": [(ldap3.MODIFY_REPLACE, [pinyin_name])],
            "employeeID": [(ldap3.MODIFY_REPLACE, [student_id])],
        }

        if paid_flag == "$":
            changes["employeeType"] = [(ldap3.MODIFY_REPLACE, ["$"])]
        elif paid_flag is None:
            changes["employeeType"] = [(ldap3.MODIFY_DELETE, [])]

        if not conn.modify(user_dn, changes):
            raise LDAPException(f"update user attributes failed: {conn.result}")

        return list(changes.keys())

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

    def list_groups(self) -> List[LdapGroup]:
        with self.connection() as conn:
            conn.search(
                search_base=self.cfg.base_dn,
                search_filter="(objectClass=group)",
                attributes=["cn", "distinguishedName", "member", "description"],
            )
            groups: List[LdapGroup] = []
            for e in conn.entries:
                groups.append(
                    LdapGroup(
                        cn=str(getattr(e, "cn", "")),
                        dn=str(getattr(e, "distinguishedName", "")),
                        description=str(getattr(e, "description", "")) if hasattr(e, "description") else None,
                        members=[str(x) for x in getattr(e, "member", [])] if hasattr(e, "member") else [],
                    )
                )
            return groups

    def list_users(self) -> List[LdapUser]:
        with self.connection() as conn:
            conn.search(
                search_base=self.cfg.base_dn,
                search_filter="(&(objectClass=user)(!(objectClass=computer)))",
                attributes=["distinguishedName", "sAMAccountName", "displayName", "userPrincipalName"],
            )
            users: List[LdapUser] = []
            for e in conn.entries:
                users.append(
                    LdapUser(
                        dn=str(getattr(e, "distinguishedName", "")),
                        sAMAccountName=str(getattr(e, "sAMAccountName", "")) if hasattr(e, "sAMAccountName") else None,
                        displayName=str(getattr(e, "displayName", "")) if hasattr(e, "displayName") else None,
                        userPrincipalName=str(getattr(e, "userPrincipalName", "")) if hasattr(e, "userPrincipalName") else None,
                    )
                )
            return users

    # ----------------------------
    # Group Tree (nested groups + users)
    # ----------------------------

    def _fetch_users_by_dn(self, dns: List[str]) -> Dict[str, LdapUser]:
        """
        按 DN 批量查用户信息。
        注意：LDAP filter 长度有限，DN 很多时需要分批。
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
                    attributes=["distinguishedName", "sAMAccountName", "displayName", "userPrincipalName"],
                )
                for e in conn.entries:
                    dn = str(getattr(e, "distinguishedName", ""))
                    if not dn:
                        continue
                    out[dn] = LdapUser(
                        dn=dn,
                        sAMAccountName=str(getattr(e, "sAMAccountName", "")) if hasattr(e, "sAMAccountName") else None,
                        displayName=str(getattr(e, "displayName", "")) if hasattr(e, "displayName") else None,
                        userPrincipalName=str(getattr(e, "userPrincipalName", "")) if hasattr(e, "userPrincipalName") else None,
                    )
            return out

    def build_group_tree(self, root_group_cn: Optional[str] = None) -> List[GroupTreeNode]:
        """
        按“组嵌套关系”构建树。
        """
        groups = self.list_groups()
        dn_to_group: Dict[str, LdapGroup] = {g.dn: g for g in groups if g.dn}

        child_groups: Dict[str, Set[str]] = {g.dn: set() for g in groups if g.dn}
        group_users: Dict[str, Set[str]] = {g.dn: set() for g in groups if g.dn}

        for g in groups:
            if not g.dn:
                continue
            for member_dn in (g.members or []):
                if member_dn in dn_to_group:
                    child_groups[g.dn].add(member_dn)
                else:
                    group_users[g.dn].add(member_dn)

        roots: List[str] = []
        if root_group_cn:
            for g in groups:
                if g.cn == root_group_cn:
                    roots = [g.dn]
                    break
            if not roots:
                return []
        else:
            referenced: Set[str] = set()
            for kids in child_groups.values():
                referenced |= set(kids)
            for g in groups:
                if g.dn and g.dn not in referenced:
                    roots.append(g.dn)

        all_user_dns: List[str] = sorted({dn for dns in group_users.values() for dn in dns})
        dn_to_user = self._fetch_users_by_dn(all_user_dns) if all_user_dns else {}

        def build_node(group_dn: str, visited: Set[str]) -> GroupTreeNode:
            if group_dn in visited:
                g = dn_to_group.get(group_dn)
                return GroupTreeNode(dn=group_dn, cn=(g.cn if g else group_dn), users=[], groups=[])

            next_visited = set(visited)
            next_visited.add(group_dn)

            g = dn_to_group.get(group_dn)
            cn = g.cn if g else group_dn

            users: List[LdapUser] = []
            for u_dn in sorted(group_users.get(group_dn, set())):
                u = dn_to_user.get(u_dn)
                if u:
                    users.append(u)

            sub_nodes: List[GroupTreeNode] = []
            for child_dn in sorted(child_groups.get(group_dn, set())):
                sub_nodes.append(build_node(child_dn, next_visited))

            return GroupTreeNode(dn=group_dn, cn=cn, users=users, groups=sub_nodes)

        return [build_node(r, set()) for r in roots]
