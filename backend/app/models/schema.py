# backend/app/models/schema.py
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional


# =========================
# Samba Models
# =========================

class Share(BaseModel):
    name: str
    path: str
    browseable: bool = True
    read_only: bool = False
    guest_ok: bool = False
    valid_users: Optional[str] = None
    write_list: Optional[str] = None


class ConfigModel(BaseModel):
    shares: List[Share]


# =========================
# LDAP Models (AD DC)
# Notes:
# - Keep existing field names: sAMAccountName / displayName / userPrincipalName
# - Add start_tls / tls_skip_verify to support 389+StartTLS or 636+LDAPS
# - Avoid mutable [] defaults for lists (use default_factory)
# =========================

class LdapConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 636

    # LDAPS: use_ssl=True (usually port 636)
    use_ssl: bool = False

    # LDAP 389 + StartTLS (commonly used if AD enforces encryption/signing)
    start_tls: bool = False

    # Lab/dev environments often use self-signed certs; skip verify for now
    tls_skip_verify: bool = True

    bind_user: str = "Administrator@EVMS.BSTU.EDU"
    bind_password: str = ""
    base_dn: str = "DC=evms,DC=bstu,DC=edu"


class LdapUser(BaseModel):
    dn: str
    sAMAccountName: Optional[str] = None
    displayName: Optional[str] = None
    userPrincipalName: Optional[str] = None
    givenName: Optional[str] = None
    employeeID: Optional[str] = None
    employeeType: Optional[str] = None


class LdapGroup(BaseModel):
    dn: str
    cn: str
    description: Optional[str] = None
    members: List[str] = Field(default_factory=list)  # member DNs


class GroupTreeNode(BaseModel):
    dn: str
    cn: str
    users: List[LdapUser] = Field(default_factory=list)
    groups: List["GroupTreeNode"] = Field(default_factory=list)


class OuTreeNode(BaseModel):
    dn: str
    ou: str
    users: List[LdapUser] = Field(default_factory=list)
    children: List["OuTreeNode"] = Field(default_factory=list)


GroupTreeNode.model_rebuild()
OuTreeNode.model_rebuild()
