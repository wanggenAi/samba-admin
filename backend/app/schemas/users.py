from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class UserAddRequest(BaseModel):
    source_username: Optional[str] = Field(default=None, max_length=64)
    username: Optional[str] = Field(default=None, max_length=64)
    password: Optional[str] = Field(default=None, max_length=256)
    student_id: str = Field(min_length=1, max_length=64)
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    display_name: Optional[str] = Field(default=None, max_length=128)
    paid_flag: Optional[str] = None
    groups: list[str] = Field(default_factory=list)
    ou_path: list[str] = Field(default_factory=list)
    sync_groups: bool = False

    @staticmethod
    def _strip_or_none(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        v = value.strip()
        return v or None

    @field_validator("source_username", "username")
    @classmethod
    def _normalize_username(cls, value: Optional[str]) -> Optional[str]:
        return cls._strip_or_none(value)

    @field_validator("student_id", "first_name", "last_name")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        v = value.strip()
        if not v:
            raise ValueError("field cannot be empty")
        return v

    @field_validator("paid_flag")
    @classmethod
    def _validate_paid_flag(cls, value: Optional[str]) -> Optional[str]:
        v = cls._strip_or_none(value)
        if v is None:
            return None
        if v != "$":
            raise ValueError("paid_flag must be '$' or empty")
        return v

    @field_validator("display_name")
    @classmethod
    def _normalize_display_name(cls, value: Optional[str]) -> Optional[str]:
        return cls._strip_or_none(value)

    @field_validator("password")
    @classmethod
    def _normalize_password(cls, value: Optional[str]) -> Optional[str]:
        return cls._strip_or_none(value)

    @field_validator("groups")
    @classmethod
    def _normalize_groups(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for raw in values:
            g = raw.strip()
            if not g:
                continue
            k = g.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(g)
        return out

    @field_validator("ou_path")
    @classmethod
    def _normalize_ou_path(cls, values: list[str]) -> list[str]:
        if len(values) > 64:
            raise ValueError("ou_path depth is too large")
        out: list[str] = []
        for raw in values:
            item = raw.strip()
            if not item:
                continue
            # UI/API must pass OU path segments only (single logical path), not raw DN fragments.
            if re.search(r"(?i)\b(ou|dc|cn)\s*=", item):
                raise ValueError("ou_path must be OU path segments, not DN fragments")
            out.append(item)
        return out


class UserAddResponse(BaseModel):
    ok: bool = True
    username: str
    created: bool
    password_updated: bool
    moved: bool = False
    moved_to_dn: Optional[str] = None
    updated_attributes: list[str] = Field(default_factory=list)
    groups_added: list[str] = Field(default_factory=list)
    groups_removed: list[str] = Field(default_factory=list)


class UserDeleteResponse(BaseModel):
    ok: bool = True
    username: str
    deleted: bool
    dn: Optional[str] = None


class UserImportItemResult(BaseModel):
    file_name: str
    line_no: int
    raw_line: str
    username: Optional[str] = None
    password: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    ou_path: list[str] = Field(default_factory=list)
    status: Literal["created", "skipped", "failed"]
    message: str


class UserImportResponse(BaseModel):
    ok: bool = True
    total_files: int
    total_lines: int
    created: int
    skipped: int
    failed: int
    results: list[UserImportItemResult] = Field(default_factory=list)
