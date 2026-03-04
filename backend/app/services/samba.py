import subprocess
import shutil
from pathlib import Path
from datetime import datetime

from ..models.schema import ConfigModel


SERVICE = "smbd"
SMB_CONF = Path("/etc/samba/smb.conf")

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
VERSIONS_DIR = DATA_DIR / "versions"

VERSIONS_DIR.mkdir(parents=True, exist_ok=True)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


# ---------------------------
# System
# ---------------------------

def get_service_status():
    p = run(["systemctl", "is-active", SERVICE])
    raw = (p.stdout or "").strip()

    return {
        "service": SERVICE,
        "active": raw == "active",
        "raw": raw
    }


# ---------------------------
# Generate smb.conf
# ---------------------------

def generate_config(payload: ConfigModel):

    lines = []

    lines.append("[global]")
    lines.append("   workgroup = WORKGROUP")
    lines.append("   server string = Samba Server")
    lines.append("   security = user")
    lines.append("")

    for s in payload.shares:

        lines.append(f"[{s.name}]")
        lines.append(f"   path = {s.path}")
        lines.append(f"   browseable = {'yes' if s.browseable else 'no'}")
        lines.append(f"   read only = {'yes' if s.read_only else 'no'}")
        lines.append(f"   guest ok = {'yes' if s.guest_ok else 'no'}")

        if s.valid_users:
            lines.append(f"   valid users = {s.valid_users}")

        if s.write_list:
            lines.append(f"   write list = {s.write_list}")

        lines.append("")

    return "\n".join(lines)


# ---------------------------
# Validate config
# ---------------------------

def validate_config(payload: ConfigModel):

    content = generate_config(payload)

    tmp = Path("/tmp/smb_test.conf")
    tmp.write_text(content)

    p = run(["testparm", "-s", str(tmp)])

    return {
        "ok": p.returncode == 0,
        "output": p.stdout + p.stderr
    }


# ---------------------------
# Apply config
# ---------------------------

def apply_config(payload: ConfigModel):

    content = generate_config(payload)

    tmp = Path("/tmp/smb_apply.conf")
    tmp.write_text(content)

    p = run(["testparm", "-s", str(tmp)])

    if p.returncode != 0:
        return {
            "ok": False,
            "output": p.stdout + p.stderr
        }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    backup = VERSIONS_DIR / f"smb_{timestamp}.conf"

    shutil.copy(SMB_CONF, backup)

    SMB_CONF.write_text(content)

    run(["systemctl", "reload", SERVICE])

    return {
        "ok": True,
        "version": backup.name
    }


# ---------------------------
# Versions
# ---------------------------

def list_versions():

    items = []

    for f in sorted(VERSIONS_DIR.glob("*.conf"), reverse=True):

        items.append({
            "id": f.name,
            "name": f.name,
            "time": f.stat().st_mtime
        })

    return items


# ---------------------------
# Rollback
# ---------------------------

def rollback_version(vid: str):

    target = VERSIONS_DIR / vid

    if not target.exists():
        return {"ok": False, "error": "version not found"}

    shutil.copy(target, SMB_CONF)

    run(["systemctl", "reload", SERVICE])

    return {"ok": True}