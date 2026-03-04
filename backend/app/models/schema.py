from pydantic import BaseModel
from typing import List, Optional


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