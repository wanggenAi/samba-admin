# backend/app/services/ldap_service.py
from __future__ import annotations

import ssl
from contextlib import contextmanager
from typing import Dict, Iterator, List, Optional, Set

import ldap3
from ldap3.core.exceptions import LDAPException

from app.core.settings import LdapSettings
from app.models.schema import GroupTreeNode, LdapGroup, LdapUser, OuTreeNode


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
        if not value or value == "[]":
            return None
        return value

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

    def create_user(
        self,
        conn: ldap3.Connection,
        username: str,
        password: str,
        parent_dn: Optional[str] = None,
    ) -> str:
        target_parent_dn = parent_dn or self._users_container_dn()
        user_dn = f"CN={ldap3.utils.dn.escape_rdn(username)},{target_parent_dn}"
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
        student_id: str,
        russian_name: str,
        pinyin_name: str,
        paid_flag: Optional[str],
    ) -> List[str]:
        base_changes: Dict[str, List[tuple[int, List[str]]]] = {
            "displayName": [(ldap3.MODIFY_REPLACE, [russian_name])],
            "givenName": [(ldap3.MODIFY_REPLACE, [pinyin_name])],
            "employeeID": [(ldap3.MODIFY_REPLACE, [student_id])],
        }

        if not conn.modify(user_dn, base_changes):
            raise LDAPException(f"update user attributes failed: {conn.result}")

        updated: List[str] = ["displayName", "givenName", "employeeID"]

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
                attributes=[
                    "distinguishedName",
                    "sAMAccountName",
                    "displayName",
                    "userPrincipalName",
                    "givenName",
                    "employeeID",
                    "employeeType",
                ],
            )
            users: List[LdapUser] = []
            for e in conn.entries:
                users.append(
                    LdapUser(
                        dn=self._entry_attr(e, "distinguishedName") or "",
                        sAMAccountName=self._entry_attr(e, "sAMAccountName"),
                        displayName=self._entry_attr(e, "displayName"),
                        userPrincipalName=self._entry_attr(e, "userPrincipalName"),
                        givenName=self._entry_attr(e, "givenName"),
                        employeeID=self._entry_attr(e, "employeeID"),
                        employeeType=self._entry_attr(e, "employeeType"),
                    )
                )
            return users

    def build_ou_tree(self) -> List[OuTreeNode]:
        with self.connection() as conn:
            conn.search(
                search_base=self.cfg.base_dn,
                search_filter="(objectClass=organizationalUnit)",
                attributes=["distinguishedName", "ou"],
            )
            ou_entries = list(conn.entries)

            conn.search(
                search_base=self.cfg.base_dn,
                search_filter="(&(objectClass=user)(!(objectClass=computer)))",
                attributes=["distinguishedName", "sAMAccountName", "displayName", "userPrincipalName"],
            )
            user_entries = list(conn.entries)

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
            parent.users.append(
                LdapUser(
                    dn=user_dn,
                    sAMAccountName=str(getattr(entry, "sAMAccountName", "")) if hasattr(entry, "sAMAccountName") else None,
                    displayName=str(getattr(entry, "displayName", "")) if hasattr(entry, "displayName") else None,
                    userPrincipalName=str(getattr(entry, "userPrincipalName", "")) if hasattr(entry, "userPrincipalName") else None,
                )
            )

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
