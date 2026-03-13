from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LdapConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 636
    use_ssl: bool = False
    start_tls: bool = False
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
    sn: Optional[str] = None
    employeeID: Optional[str] = None
    employeeType: Optional[str] = None
    whenCreated: Optional[str] = None
    whenChanged: Optional[str] = None
    lastLogon: Optional[str] = None
    lastLogoff: Optional[str] = None


class LdapGroup(BaseModel):
    dn: str
    cn: str
    description: Optional[str] = None
    members: list[str] = Field(default_factory=list)


class GroupTreeNode(BaseModel):
    dn: str
    cn: str
    users: list[LdapUser] = Field(default_factory=list)
    groups: list["GroupTreeNode"] = Field(default_factory=list)


class OuTreeNode(BaseModel):
    dn: str
    ou: str
    users: list[LdapUser] = Field(default_factory=list)
    children: list["OuTreeNode"] = Field(default_factory=list)


GroupTreeNode.model_rebuild()
OuTreeNode.model_rebuild()
