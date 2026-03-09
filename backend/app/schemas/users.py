from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class UserAddRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    student_id: str = Field(min_length=1, max_length=64)
    russian_name: str = Field(min_length=1, max_length=128)
    pinyin_name: str = Field(min_length=1, max_length=128)
    paid_flag: Optional[str] = None
    groups: list[str] = Field(default_factory=list)
    ou_path: list[str] = Field(default_factory=list)

    @field_validator("username")
    @classmethod
    def _normalize_username(cls, value: str) -> str:
        v = value.strip()
        if not v:
            raise ValueError("username cannot be empty")
        return v

    @field_validator("student_id", "russian_name", "pinyin_name")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        v = value.strip()
        if not v:
            raise ValueError("field cannot be empty")
        return v

    @field_validator("paid_flag")
    @classmethod
    def _validate_paid_flag(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        v = value.strip()
        if v == "":
            return None
        if v != "$":
            raise ValueError("paid_flag must be '$' or empty")
        return v

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
        out: list[str] = []
        for raw in values:
            item = raw.strip()
            if item:
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
