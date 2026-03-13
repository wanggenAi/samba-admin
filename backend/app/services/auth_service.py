from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
from fastapi import HTTPException

from ..core.settings import settings

PBKDF2_ITERATIONS = 120_000
JWT_ALG = "HS256"
PERMISSION_NAME_RE = re.compile(r"^[a-z0-9._-]+$")

BUILTIN_PERMISSIONS: dict[str, str] = {
    "dashboard.view": "View dashboard and LDAP health widgets",
    "users.view": "View users page and user list",
    "users.create": "Create LDAP users",
    "users.edit": "Edit LDAP users",
    "users.delete": "Delete LDAP users",
    "users.import": "Import users from TXT",
    "users.export": "Export users to CSV",
    "ous.view": "View OU management page and OU tree",
    "ous.create": "Create organizational units",
    "ous.rename": "Rename organizational units",
    "ous.delete": "Delete organizational units",
    "config.view": "View config placeholder page",
    "versions.view": "View versions placeholder page",
    "system.manage": "Manage local auth users, roles, and permissions",
}

BUILTIN_ROLES: list[dict[str, Any]] = [
    {
        "name": "super_admin",
        "description": "Full access to all features",
        "permissions": ["*"],
        "builtin": True,
    },
    {
        "name": "operator",
        "description": "Daily operations for users and OUs",
        "permissions": [
            "dashboard.view",
            "users.view",
            "users.create",
            "users.edit",
            "users.delete",
            "users.import",
            "users.export",
            "ous.view",
            "ous.create",
            "ous.rename",
            "ous.delete",
            "config.view",
            "versions.view",
        ],
        "builtin": True,
    },
    {
        "name": "viewer",
        "description": "Read-only access to dashboard and lists",
        "permissions": [
            "dashboard.view",
            "users.view",
            "ous.view",
            "config.view",
            "versions.view",
        ],
        "builtin": True,
    },
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256$%d$%s$%s" % (
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(dk).decode("ascii"),
    )


def _verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iter_s, salt_b64, hash_b64 = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iter_s)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(hash_b64.encode("ascii"))
    except Exception:
        return False

    current = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(current, expected)


class AuthService:
    def __init__(self, data_file: Path):
        self.data_file = data_file
        self._lock = threading.Lock()
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.data_file.exists():
            initial_user = {
                "username": "admin",
                "password_hash": _hash_password("admin123"),
                "roles": ["super_admin"],
                "disabled": False,
                "created_at": _iso_now(),
                "updated_at": _iso_now(),
            }
            payload = {
                "users": [initial_user],
                "roles": BUILTIN_ROLES,
                "permissions": [],
                "meta": {
                    "initialized_at": _iso_now(),
                    "default_admin_username": "admin",
                },
            }
            self.data_file.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
            return

        data = self._read()
        changed = False
        if "roles" not in data or not isinstance(data.get("roles"), list):
            data["roles"] = BUILTIN_ROLES
            changed = True
        if "users" not in data or not isinstance(data.get("users"), list):
            data["users"] = []
            changed = True
        if "permissions" not in data or not isinstance(data.get("permissions"), list):
            data["permissions"] = []
            changed = True
        if changed:
            self._write(data)

    def _read(self) -> dict[str, Any]:
        try:
            raw = self.data_file.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as err:
            raise HTTPException(status_code=500, detail=f"auth storage read failed: {err}")
        if not isinstance(data, dict):
            raise HTTPException(status_code=500, detail="auth storage format invalid")
        return data

    def _write(self, data: dict[str, Any]) -> None:
        tmp = self.data_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
        tmp.replace(self.data_file)

    @staticmethod
    def _sanitize_user(u: dict[str, Any], permissions: list[str]) -> dict[str, Any]:
        return {
            "username": u["username"],
            "roles": list(u.get("roles", [])),
            "disabled": bool(u.get("disabled", False)),
            "permissions": permissions,
            "created_at": u.get("created_at"),
            "updated_at": u.get("updated_at"),
        }

    @staticmethod
    def _validate_username(username: str) -> str:
        v = username.strip()
        if not v:
            raise HTTPException(status_code=400, detail="username is required")
        if len(v) > 64:
            raise HTTPException(status_code=400, detail="username too long")
        return v

    @staticmethod
    def _validate_role_name(name: str) -> str:
        v = name.strip()
        if not v:
            raise HTTPException(status_code=400, detail="role name is required")
        if len(v) > 64:
            raise HTTPException(status_code=400, detail="role name too long")
        return v

    @staticmethod
    def _validate_permission_name(name: str) -> str:
        v = name.strip()
        if not v:
            raise HTTPException(status_code=400, detail="permission name is required")
        if len(v) > 64:
            raise HTTPException(status_code=400, detail="permission name too long")
        if not PERMISSION_NAME_RE.match(v):
            raise HTTPException(status_code=400, detail="invalid permission name format")
        return v

    def _permission_map(self, data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for name, desc in BUILTIN_PERMISSIONS.items():
            out[name] = {"name": name, "description": desc, "builtin": True}

        for item in data.get("permissions", []):
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            if name in out:
                continue
            out[name] = {
                "name": name,
                "description": str(item.get("description", "")).strip(),
                "builtin": False,
            }
        return out

    def _normalize_permissions(self, values: list[str], data: dict[str, Any]) -> list[str]:
        available = self._permission_map(data)
        out: list[str] = []
        seen: set[str] = set()
        for raw in values:
            p = str(raw).strip()
            if not p:
                continue
            if p != "*" and p not in available:
                raise HTTPException(status_code=400, detail=f"unknown permission: {p}")
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
        return out

    def _resolve_role_map(self, data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        roles = data.get("roles", [])
        if not isinstance(roles, list):
            raise HTTPException(status_code=500, detail="roles format invalid")
        role_map: dict[str, dict[str, Any]] = {}
        for r in roles:
            name = str(r.get("name", "")).strip()
            if not name:
                continue
            role_map[name] = r
        return role_map

    def _collect_permissions(self, role_names: list[str], role_map: dict[str, dict[str, Any]]) -> list[str]:
        perms: list[str] = []
        seen: set[str] = set()
        for role_name in role_names:
            role = role_map.get(role_name)
            if not role:
                continue
            for raw in role.get("permissions", []):
                p = str(raw).strip()
                if not p or p in seen:
                    continue
                seen.add(p)
                perms.append(p)
        return perms

    def list_permissions(self) -> list[dict[str, Any]]:
        data = self._read()
        m = self._permission_map(data)
        out = list(m.values())
        out.sort(key=lambda x: (0 if x.get("builtin") else 1, str(x.get("name", ""))))
        return out

    def create_permission(self, name: str, description: str) -> dict[str, Any]:
        perm_name = self._validate_permission_name(name)
        with self._lock:
            data = self._read()
            m = self._permission_map(data)
            if perm_name in m:
                raise HTTPException(status_code=409, detail="permission already exists")
            item = {"name": perm_name, "description": description.strip()}
            data.setdefault("permissions", []).append(item)
            self._write(data)
            return {"name": item["name"], "description": item["description"], "builtin": False}

    def update_permission(self, name: str, description: str) -> dict[str, Any]:
        perm_name = self._validate_permission_name(name)
        with self._lock:
            data = self._read()
            if perm_name in BUILTIN_PERMISSIONS:
                raise HTTPException(status_code=400, detail="cannot edit builtin permission")
            for item in data.get("permissions", []):
                if str(item.get("name", "")).strip() != perm_name:
                    continue
                item["description"] = description.strip()
                self._write(data)
                return {"name": perm_name, "description": item["description"], "builtin": False}
        raise HTTPException(status_code=404, detail="permission not found")

    def delete_permission(self, name: str) -> dict[str, Any]:
        perm_name = self._validate_permission_name(name)
        with self._lock:
            data = self._read()
            if perm_name in BUILTIN_PERMISSIONS:
                raise HTTPException(status_code=400, detail="cannot delete builtin permission")

            for role in data.get("roles", []):
                if perm_name in (role.get("permissions") or []):
                    raise HTTPException(status_code=409, detail="permission is assigned to roles")

            perms = data.get("permissions", [])
            for idx, item in enumerate(perms):
                if str(item.get("name", "")).strip() != perm_name:
                    continue
                perms.pop(idx)
                self._write(data)
                return {"ok": True, "deleted": perm_name}
        raise HTTPException(status_code=404, detail="permission not found")

    def list_roles(self) -> list[dict[str, Any]]:
        data = self._read()
        out: list[dict[str, Any]] = []
        for role in data.get("roles", []):
            out.append(
                {
                    "name": role.get("name"),
                    "description": role.get("description"),
                    "permissions": list(role.get("permissions", [])),
                    "builtin": bool(role.get("builtin", False)),
                }
            )
        return out

    def create_role(self, name: str, description: str, permissions: list[str]) -> dict[str, Any]:
        role_name = self._validate_role_name(name)
        with self._lock:
            data = self._read()
            perms = self._normalize_permissions(permissions, data)
            if not perms:
                raise HTTPException(status_code=400, detail="role permissions cannot be empty")
            role_map = self._resolve_role_map(data)
            if role_name in role_map:
                raise HTTPException(status_code=409, detail="role already exists")
            role = {
                "name": role_name,
                "description": description.strip(),
                "permissions": perms,
                "builtin": False,
            }
            data.setdefault("roles", []).append(role)
            self._write(data)
            return role

    def update_role(self, role_name: str, description: str | None, permissions: list[str] | None) -> dict[str, Any]:
        name = self._validate_role_name(role_name)
        with self._lock:
            data = self._read()
            roles = data.get("roles", [])
            for role in roles:
                if role.get("name") != name:
                    continue
                if role.get("builtin", False) and name == "super_admin":
                    raise HTTPException(status_code=400, detail="cannot modify builtin super_admin role")
                if description is not None:
                    role["description"] = description.strip()
                if permissions is not None:
                    perms = self._normalize_permissions(permissions, data)
                    if not perms:
                        raise HTTPException(status_code=400, detail="role permissions cannot be empty")
                    role["permissions"] = perms
                self._write(data)
                return {
                    "name": role.get("name"),
                    "description": role.get("description"),
                    "permissions": list(role.get("permissions", [])),
                    "builtin": bool(role.get("builtin", False)),
                }
        raise HTTPException(status_code=404, detail="role not found")

    def delete_role(self, role_name: str) -> dict[str, Any]:
        name = self._validate_role_name(role_name)
        with self._lock:
            data = self._read()
            roles = data.get("roles", [])
            for idx, role in enumerate(roles):
                if role.get("name") != name:
                    continue
                if bool(role.get("builtin", False)):
                    raise HTTPException(status_code=400, detail="cannot delete builtin role")
                for user in data.get("users", []):
                    if name in (user.get("roles") or []):
                        raise HTTPException(status_code=409, detail="role is assigned to users")
                removed = roles.pop(idx)
                self._write(data)
                return {"ok": True, "deleted": removed.get("name")}
        raise HTTPException(status_code=404, detail="role not found")

    def list_users(self) -> list[dict[str, Any]]:
        data = self._read()
        role_map = self._resolve_role_map(data)
        out: list[dict[str, Any]] = []
        for user in data.get("users", []):
            perms = self._collect_permissions(list(user.get("roles", [])), role_map)
            out.append(self._sanitize_user(user, perms))
        return out

    def _validate_roles_exist(self, roles: list[str], role_map: dict[str, dict[str, Any]]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for raw in roles:
            role_name = self._validate_role_name(raw)
            if role_name in seen:
                continue
            if role_name not in role_map:
                raise HTTPException(status_code=400, detail=f"unknown role: {role_name}")
            seen.add(role_name)
            out.append(role_name)
        if not out:
            raise HTTPException(status_code=400, detail="at least one role is required")
        return out

    def create_user(self, username: str, password: str, roles: list[str], disabled: bool = False) -> dict[str, Any]:
        user_name = self._validate_username(username)
        if not password:
            raise HTTPException(status_code=400, detail="password is required")
        with self._lock:
            data = self._read()
            role_map = self._resolve_role_map(data)
            final_roles = self._validate_roles_exist(roles, role_map)
            for user in data.get("users", []):
                if user.get("username", "").lower() == user_name.lower():
                    raise HTTPException(status_code=409, detail="user already exists")
            now = _iso_now()
            new_user = {
                "username": user_name,
                "password_hash": _hash_password(password),
                "roles": final_roles,
                "disabled": bool(disabled),
                "created_at": now,
                "updated_at": now,
            }
            data.setdefault("users", []).append(new_user)
            self._write(data)
            perms = self._collect_permissions(final_roles, role_map)
            return self._sanitize_user(new_user, perms)

    def update_user(
        self,
        username: str,
        password: str | None = None,
        roles: list[str] | None = None,
        disabled: bool | None = None,
    ) -> dict[str, Any]:
        name = self._validate_username(username)
        with self._lock:
            data = self._read()
            role_map = self._resolve_role_map(data)
            users = data.get("users", [])
            for user in users:
                if user.get("username") != name:
                    continue
                if roles is not None:
                    user["roles"] = self._validate_roles_exist(roles, role_map)
                if disabled is not None:
                    user["disabled"] = bool(disabled)
                if password is not None:
                    if not password:
                        raise HTTPException(status_code=400, detail="password cannot be empty")
                    user["password_hash"] = _hash_password(password)
                user["updated_at"] = _iso_now()
                self._write(data)
                perms = self._collect_permissions(list(user.get("roles", [])), role_map)
                return self._sanitize_user(user, perms)
        raise HTTPException(status_code=404, detail="user not found")

    def delete_user(self, username: str) -> dict[str, Any]:
        name = self._validate_username(username)
        with self._lock:
            data = self._read()
            users = data.get("users", [])
            for idx, user in enumerate(users):
                if user.get("username") != name:
                    continue
                users.pop(idx)
                self._write(data)
                return {"ok": True, "deleted": name}
        raise HTTPException(status_code=404, detail="user not found")

    def authenticate(self, username: str, password: str) -> dict[str, Any]:
        user_name = self._validate_username(username)
        if not password:
            raise HTTPException(status_code=400, detail="password is required")
        data = self._read()
        role_map = self._resolve_role_map(data)
        for user in data.get("users", []):
            if user.get("username", "").lower() != user_name.lower():
                continue
            if bool(user.get("disabled", False)):
                raise HTTPException(status_code=403, detail="user is disabled")
            if not _verify_password(password, user.get("password_hash", "")):
                break
            perms = self._collect_permissions(list(user.get("roles", [])), role_map)
            return self._sanitize_user(user, perms)
        raise HTTPException(status_code=401, detail="invalid username or password")

    def issue_token(self, user: dict[str, Any]) -> str:
        now = _utc_now()
        exp = now + timedelta(minutes=max(1, settings.jwt_expire_minutes))
        payload = {
            "sub": user["username"],
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "roles": list(user.get("roles", [])),
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALG)

    def decode_token(self, token: str) -> dict[str, Any]:
        try:
            data = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALG])
            if not isinstance(data, dict):
                raise ValueError("payload invalid")
            return data
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="token expired")
        except Exception:
            raise HTTPException(status_code=401, detail="invalid token")

    def get_user(self, username: str) -> dict[str, Any]:
        name = self._validate_username(username)
        data = self._read()
        role_map = self._resolve_role_map(data)
        for user in data.get("users", []):
            if user.get("username") != name:
                continue
            if bool(user.get("disabled", False)):
                raise HTTPException(status_code=403, detail="user is disabled")
            perms = self._collect_permissions(list(user.get("roles", [])), role_map)
            return self._sanitize_user(user, perms)
        raise HTTPException(status_code=401, detail="user not found")

    @staticmethod
    def has_permission(user: dict[str, Any], permission: str) -> bool:
        perms = set(user.get("permissions") or [])
        return "*" in perms or permission in perms


auth_service = AuthService(settings.samba.data_dir / "rbac.json")
