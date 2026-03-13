from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Share(BaseModel):
    name: str
    path: str
    browseable: bool = True
    read_only: bool = False
    guest_ok: bool = False
    valid_users: Optional[str] = None
    write_list: Optional[str] = None


class ConfigModel(BaseModel):
    shares: list[Share]
