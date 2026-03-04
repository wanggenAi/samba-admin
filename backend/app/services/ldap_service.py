# backend/app/services/ldap_service.py
from __future__ import annotations

from typing import List, Optional, Dict, Set
import ssl

import ldap3
from ldap3.core.exceptions import LDAPException, LDAPSocketOpenError

from app.core.settings import LdapSettings
from app.models.schema import LdapGroup, LdapUser, GroupTreeNode


class LdapService:
    def __init__(self, cfg: LdapSettings):
        self.cfg = cfg

    def _make_tls(self) -> ldap3.Tls:
        if getattr(self.cfg, "tls_skip_verify", True):
            return ldap3.Tls(validate=ssl.CERT_NONE)
        return ldap3.Tls(validate=ssl.CERT_REQUIRED)

    def _connect(self) -> ldap3.Connection:

        tls = self._make_tls() if self.cfg.use_ssl else None

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
            auto_bind=True,  # 关键
        )

        return conn

    def ping(self) -> None:
        conn = self._connect()
        try:
            conn.search(
                search_base=self.cfg.base_dn,
                search_filter="(objectClass=*)",
                search_scope=ldap3.BASE,
                attributes=["defaultNamingContext"],
            )
        finally:
            conn.unbind()

    # ----------------------------
    # Groups / Users
    # ----------------------------

    def list_groups(self) -> List[LdapGroup]:
        conn = self._connect()
        try:
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
        finally:
            conn.unbind()

    def list_users(self) -> List[LdapUser]:
        conn = self._connect()
        try:
            # 过滤掉 computer 账户
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
        finally:
            conn.unbind()

    # ----------------------------
    # Group Tree (nested groups + users)
    # ----------------------------

    def _fetch_users_by_dn(self, dns: List[str]) -> Dict[str, LdapUser]:
        """
        按 DN 批量查用户信息。
        注意：LDAP filter 长度有限，DN 很多时需要分批。
        """
        conn = self._connect()
        try:
            out: Dict[str, LdapUser] = {}
            batch_size = 20  # 保守点
            for i in range(0, len(dns), batch_size):
                batch = dns[i : i + batch_size]
                # (|(distinguishedName=dn1)(distinguishedName=dn2)...)
                or_filter = "(|" + "".join([f"(distinguishedName={ldap3.utils.conv.escape_filter_chars(dn)})" for dn in batch]) + ")"
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
        finally:
            conn.unbind()

    def build_group_tree(self, root_group_cn: Optional[str] = None) -> List[GroupTreeNode]:
        """
        按“组嵌套关系”构建树：
        - group.member 里既可能有 user DN，也可能有 group DN
        - 我们先构建 group->subgroup 的树
        - 再把每个组直属成员中的 user DN 解析成 users 列表

        注意：这不是 OU 树，是“组嵌套树”。
        """
        groups = self.list_groups()
        dn_to_group: Dict[str, LdapGroup] = {g.dn: g for g in groups if g.dn}

        # group_dn -> child_group_dns
        child_groups: Dict[str, Set[str]] = {g.dn: set() for g in groups if g.dn}
        # group_dn -> user_dns
        group_users: Dict[str, Set[str]] = {g.dn: set() for g in groups if g.dn}

        for g in groups:
            if not g.dn:
                continue
            for member_dn in (g.members or []):
                if member_dn in dn_to_group:
                    child_groups[g.dn].add(member_dn)
                else:
                    # 先当作 user dn 收集，后面批量查证
                    group_users[g.dn].add(member_dn)

        # roots
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
            for parent_dn, kids in child_groups.items():
                referenced |= set(kids)
            for g in groups:
                if g.dn and g.dn not in referenced:
                    roots.append(g.dn)

        # 批量把可能的 user dn 查出来（只查“在任何组中出现过的非group DN”）
        all_user_dns: List[str] = sorted({dn for dns in group_users.values() for dn in dns})
        dn_to_user = self._fetch_users_by_dn(all_user_dns) if all_user_dns else {}

        def build_node(group_dn: str, visited: Set[str]) -> GroupTreeNode:
            if group_dn in visited:
                # 防止循环引用（AD 里组嵌套可能出现）
                g = dn_to_group.get(group_dn)
                return GroupTreeNode(dn=group_dn, cn=(g.cn if g else group_dn), users=[], groups=[])

            visited = set(visited)
            visited.add(group_dn)

            g = dn_to_group.get(group_dn)
            cn = g.cn if g else group_dn

            # users: 只放这个组“直属成员”里的用户
            users: List[LdapUser] = []
            for u_dn in sorted(group_users.get(group_dn, set())):
                u = dn_to_user.get(u_dn)
                if u:
                    users.append(u)

            # sub groups
            sub_nodes: List[GroupTreeNode] = []
            for child_dn in sorted(child_groups.get(group_dn, set())):
                sub_nodes.append(build_node(child_dn, visited))

            return GroupTreeNode(dn=group_dn, cn=cn, users=users, groups=sub_nodes)

        return [build_node(r, set()) for r in roots]