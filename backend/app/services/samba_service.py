from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader

from ..core import settings
from ..models.schema import ConfigModel


# ----------------------------
# Jinja2 template engine
# ----------------------------

def _get_jinja_env() -> Environment:
    templates_dir = settings.samba.templates_dir
    if not templates_dir.exists():
        raise HTTPException(
            status_code=500,
            detail=f"templates dir not found: {templates_dir}",
        )
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_smb_conf(payload: ConfigModel) -> str:
    """
    Render smb.conf using Jinja2 template.
    Template: templates/smb.conf.j2
    """
    env = _get_jinja_env()
    tpl = env.get_template("smb.conf.j2")

    # 注意：shares 是 List[Share]，需要转 dict 才方便模板处理
    shares = [s.model_dump() for s in payload.shares]
    return tpl.render(shares=shares)


# ----------------------------
# helpers
# ----------------------------

def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def _ensure_dirs() -> None:
    settings.samba.data_dir.mkdir(parents=True, exist_ok=True)
    settings.samba.versions_dir.mkdir(parents=True, exist_ok=True)


def _write_tmp_conf(content: str) -> Path:
    tmp = settings.samba.tmp_conf_path
    tmp.write_text(content, encoding="utf-8")
    return tmp


def _test_conf(conf_path: Path) -> str:
    """
    Use testparm to validate config.
    NOTE: On macOS probably don't have `testparm`.
    So this endpoint is mainly for Ubuntu (server side).
    """
    cmd = settings.samba.testparm_cmd
    p = _run([cmd, "-s", str(conf_path)])
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        raise HTTPException(status_code=400, detail={"stage": "validate", "output": out})
    return out


def _backup_current_conf() -> Path:
    _ensure_dirs()
    smb_conf = settings.samba.smb_conf_path

    if not smb_conf.exists():
        raise HTTPException(
            status_code=500,
            detail=f"smb.conf not found at {smb_conf}. Check SAMBA_CONF env.",
        )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = settings.samba.versions_dir / f"smb.conf.{ts}.bak"
    shutil.copy2(smb_conf, backup_path)
    return backup_path


def _reload_service() -> str:
    """
    AD DC mode: reload samba-ad-dc
    """
    svc = settings.samba.service_name
    p = _run(["systemctl", "reload", svc])
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={"stage": "reload", "service": svc, "output": out},
        )
    return out or "reload ok"


# ----------------------------
# Public API (called by routers)
# ----------------------------

def get_service_status() -> dict:
    svc = settings.samba.service_name
    p = _run(["systemctl", "is-active", svc])
    raw = (p.stdout or "").strip()
    return {"service": svc, "active": raw == "active", "raw": raw}


def validate_config(payload: ConfigModel) -> dict:
    content = render_smb_conf(payload)
    tmp = _write_tmp_conf(content)
    out = _test_conf(tmp)
    return {"ok": True, "output": out}


def apply_config(payload: ConfigModel) -> dict:
    if not settings.samba.allow_apply:
        raise HTTPException(
            status_code=403,
            detail="apply is disabled (set ALLOW_APPLY=true on server if needed)."
        )
    smb_conf = settings.samba.smb_conf_path
    content = render_smb_conf(payload)
    tmp = _write_tmp_conf(content)

    validate_out = _test_conf(tmp)
    backup = _backup_current_conf()

    try:
        shutil.copy2(tmp, smb_conf)
        reload_out = _reload_service()
        (settings.samba.data_dir / "last_apply.json").write_text(
            payload.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return {
            "ok": True,
            "backup": str(backup),
            "validate": validate_out,
            "reload": reload_out,
        }
    except HTTPException as e:
        # rollback
        shutil.copy2(backup, smb_conf)
        _run(["systemctl", "reload", settings.samba.service_name])
        raise e


def list_versions() -> list[dict]:
    _ensure_dirs()
    items = sorted(settings.samba.versions_dir.glob("smb.conf.*.bak"), reverse=True)
    return [{"id": p.name, "path": str(p), "mtime": p.stat().st_mtime} for p in items]


def rollback_version(vid: str) -> dict:
    _ensure_dirs()
    p = settings.samba.versions_dir / vid
    if not p.exists():
        raise HTTPException(status_code=404, detail="version not found")

    smb_conf = settings.samba.smb_conf_path
    backup = _backup_current_conf()
    shutil.copy2(p, smb_conf)

    try:
        out = _reload_service()
        return {"ok": True, "backup": str(backup), "rolled_back_to": vid, "output": out}
    except HTTPException as e:
        shutil.copy2(backup, smb_conf)
        _run(["systemctl", "reload", settings.samba.service_name])
        raise e