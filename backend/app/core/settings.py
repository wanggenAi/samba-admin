# backend/app/core/settings.py
from __future__ import annotations

import os
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

# 加载 .env（本地开发用；服务器建议用 systemd EnvironmentFile 或环境变量注入）
load_dotenv()


def _bool(val: str | None, default: bool = False) -> bool:
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
    # AD DC 模式下：使用 samba-ad-dc 这个服务（不是 smbd）
    service_name: str = os.getenv("SAMBA_SERVICE", "samba-ad-dc")

    # Ubuntu AD DC 默认 smb.conf 路径（通常还是这个）
    smb_conf_path: Path = Path(os.getenv("SAMBA_CONF", "/etc/samba/smb.conf"))

    # 版本备份目录（默认 backend/app/data/versions）
    data_dir: Path = Path(
        os.getenv("APP_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data"))
    )
    versions_dir: Path = Path(
        os.getenv("APP_VERSIONS_DIR", str(Path(__file__).resolve().parents[1] / "data" / "versions"))
    )

    # Jinja2 模板目录（默认 backend/templates）
    templates_dir: Path = Path(
        os.getenv("SAMBA_TEMPLATES_DIR", str(Path(__file__).resolve().parents[2] / "templates"))
    )

    # 临时生成配置文件位置
    tmp_conf_path: Path = Path(os.getenv("SAMBA_TMP_CONF", "/tmp/smb.conf.generated"))

    # 校验配置命令（AD DC 也可以用 testparm）
    testparm_cmd: str = os.getenv("SAMBA_TESTPARM", "testparm")

    # 是否允许写 smb.conf / reload（生产环境默认 false）
    allow_apply: bool = _bool(os.getenv("ALLOW_APPLY"), default=False)

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.versions_dir.mkdir(parents=True, exist_ok=True)


class LdapSettings(BaseModel):
    # 你的 AD DC 机器 IP（Ubuntu 这台）
    host: str = os.getenv("LDAP_HOST", "10.211.55.10")

    # AD 的 LDAP：389（LDAP）/ 636（LDAPS）
    port: int = int(os.getenv("LDAP_PORT", "389"))

    # 是否使用 SSL（LDAPS 636）
    use_ssl: bool = _bool(os.getenv("LDAP_USE_SSL"), default=False)

    # StartTLS（通常是 389 上升级加密；和 use_ssl 二选一）
    # 兼容 LDAP_STARTTLS / LDAP_START_TLS 两种写法
    start_tls: bool = _bool(
        os.getenv("LDAP_START_TLS", os.getenv("LDAP_STARTTLS")),
        default=False,
    )

    # 是否跳过证书校验（实验环境常用；生产环境建议 false + 正确证书）
    tls_skip_verify: bool = _bool(os.getenv("LDAP_TLS_SKIP_VERIFY"), default=True)

    # AD bind 用户（你现在用的是 UPN）
    bind_user: str = os.getenv("LDAP_BIND_USER", "Administrator@EVMS.BSTU.EDU")

    # 部署时用环境变量注入（不要写死）
    bind_password: str = os.getenv("LDAP_BIND_PASSWORD", "")

    # 根 DN
    base_dn: str = os.getenv("LDAP_BASE_DN", "DC=evms,DC=bstu,DC=edu")

    # 用户默认创建容器；留空时使用 CN=Users,<base_dn>
    user_container_dn: str | None = os.getenv("LDAP_USER_CONTAINER_DN") or None

    # 用户 UPN 后缀；留空时从 base_dn 推导
    user_upn_suffix: str | None = os.getenv("LDAP_USER_UPN_SUFFIX") or None

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


settings = Settings()

# Ensure local dirs exist
settings.samba.ensure_dirs()
settings.ldap.normalized()
