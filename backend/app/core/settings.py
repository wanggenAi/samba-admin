# backend/app/core/settings.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from dotenv import load_dotenv

# Load .env for local development; in production prefer systemd EnvironmentFile or injected env vars
load_dotenv()


def _bool(val: Optional[str], default: bool = False) -> bool:
    """
    Parse env boolean values safely.
    Accept: 1/0, true/false, yes/no, y/n, on/off
    """
    if val is None:
        return default
    v = val.strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    return default


class SambaSettings(BaseModel):
    # In AD DC mode, use samba-ad-dc service (not smbd)
    service_name: str = os.getenv("SAMBA_SERVICE", "samba-ad-dc")

    # Default smb.conf path on Ubuntu AD DC (commonly this path)
    smb_conf_path: Path = Path(os.getenv("SAMBA_CONF", "/etc/samba/smb.conf"))

    # Version backup directory (defaults to backend/app/data/versions)
    data_dir: Path = Path(
        os.getenv("APP_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data"))
    )
    versions_dir: Path = Path(
        os.getenv("APP_VERSIONS_DIR", str(Path(__file__).resolve().parents[1] / "data" / "versions"))
    )

    # Jinja2 templates directory (defaults to backend/templates)
    templates_dir: Path = Path(
        os.getenv("SAMBA_TEMPLATES_DIR", str(Path(__file__).resolve().parents[2] / "templates"))
    )

    # Temporary generated config file path
    tmp_conf_path: Path = Path(os.getenv("SAMBA_TMP_CONF", "/tmp/smb.conf.generated"))

    # Config validation command (testparm also works for AD DC)
    testparm_cmd: str = os.getenv("SAMBA_TESTPARM", "testparm")

    # Whether writing smb.conf / reload is allowed (default false in production)
    allow_apply: bool = _bool(os.getenv("ALLOW_APPLY"), default=False)

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.versions_dir.mkdir(parents=True, exist_ok=True)


class LdapSettings(BaseModel):
    # AD DC host IP (this Ubuntu server)
    host: str = os.getenv("LDAP_HOST", "10.211.55.10")

    # AD LDAP ports: 389 (LDAP) / 636 (LDAPS)
    port: int = int(os.getenv("LDAP_PORT", "389"))

    # Whether to use SSL (LDAPS 636)
    use_ssl: bool = _bool(os.getenv("LDAP_USE_SSL"), default=False)

    # StartTLS (typically upgrade encryption on 389; mutually exclusive with use_ssl)
    # Support both LDAP_STARTTLS and LDAP_START_TLS env names
    start_tls: bool = _bool(
        os.getenv("LDAP_START_TLS", os.getenv("LDAP_STARTTLS")),
        default=False,
    )

    # Whether to skip cert verification (common in labs; use false + proper certs in production)
    tls_skip_verify: bool = _bool(os.getenv("LDAP_TLS_SKIP_VERIFY"), default=True)

    # AD bind user (currently using UPN)
    bind_user: str = os.getenv("LDAP_BIND_USER", "Administrator@EVMS.BSTU.EDU")

    # Inject via environment variables in deployment (do not hardcode)
    bind_password: str = os.getenv("LDAP_BIND_PASSWORD", "")

    # Base DN
    base_dn: str = os.getenv("LDAP_BASE_DN", "DC=evms,DC=bstu,DC=edu")

    # Default user container; when empty use CN=Users,<base_dn>
    user_container_dn: Optional[str] = os.getenv("LDAP_USER_CONTAINER_DN") or None

    # User UPN suffix; derive from base_dn when empty
    user_upn_suffix: Optional[str] = os.getenv("LDAP_USER_UPN_SUFFIX") or None

    def normalized(self) -> "LdapSettings":
        """
        Small normalization: if use_ssl is True, start_tls should be False.
        """
        if self.use_ssl and self.start_tls:
            # LDAPS and StartTLS are mutually exclusive; prefer LDAPS if explicitly enabled.
            self.start_tls = False
        if self.user_container_dn is not None:
            v = self.user_container_dn.strip()
            self.user_container_dn = v or None
        if self.user_upn_suffix is not None:
            v = self.user_upn_suffix.strip()
            self.user_upn_suffix = v or None
        return self


class Settings(BaseModel):
    samba: SambaSettings = SambaSettings()
    ldap: LdapSettings = LdapSettings()
    jwt_secret: str = os.getenv("APP_JWT_SECRET", "change-me-in-production")
    jwt_expire_minutes: int = int(os.getenv("APP_JWT_EXPIRE_MINUTES", "480"))


settings = Settings()

# Ensure local dirs exist
settings.samba.ensure_dirs()
settings.ldap.normalized()
