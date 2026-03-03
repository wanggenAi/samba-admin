from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from pathlib import Path
from datetime import datetime
import subprocess
import shutil
from jinja2 import Environment, FileSystemLoader

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
VERSIONS_DIR = DATA_DIR / "versions"
TEMPLATES_DIR = APP_DIR / "templates"

# Ubuntu 上 Samba 配置与服务名
SMB_CONF = Path("/etc/samba/smb.conf")
SERVICE = "smbd"

DATA_DIR.mkdir(exist_ok=True)
VERSIONS_DIR.mkdir(parents=True, exist_ok=True)

env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)

class Share(BaseModel):
    name: str = Field(..., pattern=r"^[a-zA-Z0-9_\-]+$")
    path: str = Field(..., pattern=r"^/.*")
    browseable: bool = True
    read_only: bool = False
    guest_ok: bool = True
    valid_users: Optional[str] = None  # e.g. "user1,user2" or "user1 user2"
    write_list: Optional[str] = None

class ConfigModel(BaseModel):
    shares: List[Share]

app = FastAPI(title="Samba Admin API")

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

DIST_DIR = APP_DIR / "dist"

if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

    @app.get("/")
    async def serve_spa():
        return FileResponse(str(DIST_DIR / "index.html"))

def run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)

def render_conf(model: ConfigModel) -> str:
    tpl = env.get_template("smb.conf.j2")
    return tpl.render(shares=[s.model_dump() for s in model.shares])

def backup_current() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = VERSIONS_DIR / f"smb.conf.{ts}.bak"
    shutil.copy2(SMB_CONF, backup_path)
    return backup_path

def write_tmp_conf(content: str) -> Path:
    tmp = Path("/tmp/smb.conf.generated")
    tmp.write_text(content, encoding="utf-8")
    return tmp

def test_conf(conf_path: Path) -> str:
    p = run(["testparm", "-s", str(conf_path)])
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        raise HTTPException(status_code=400, detail={"stage": "validate", "output": out})
    return out

def apply_conf(conf_path: Path) -> str:
    shutil.copy2(conf_path, SMB_CONF)
    p = run(["systemctl", "reload", SERVICE])
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        raise HTTPException(status_code=500, detail={"stage": "reload", "output": out})
    return out or "reload ok"

@app.get("/api/system/status")
def status():
    p = run(["systemctl", "is-active", SERVICE])
    return {"service": SERVICE, "active": p.stdout.strip() == "active", "raw": p.stdout.strip()}

@app.post("/api/config/validate")
def validate(model: ConfigModel):
    content = render_conf(model)
    tmp = write_tmp_conf(content)
    out = test_conf(tmp)
    return {"ok": True, "output": out}

@app.post("/api/config/apply")
def apply(model: ConfigModel):
    content = render_conf(model)
    tmp = write_tmp_conf(content)

    # 1) validate
    validate_out = test_conf(tmp)

    # 2) backup
    backup = backup_current()

    # 3) apply + rollback on failure
    try:
        reload_out = apply_conf(tmp)
        (DATA_DIR / "model.json").write_text(model.model_dump_json(indent=2), encoding="utf-8")
        return {"ok": True, "backup": str(backup), "validate": validate_out, "reload": reload_out}
    except HTTPException as e:
        shutil.copy2(backup, SMB_CONF)
        run(["systemctl", "reload", SERVICE])
        raise e

@app.get("/api/versions")
def versions():
    items = sorted(VERSIONS_DIR.glob("smb.conf.*.bak"), reverse=True)
    return [{"id": p.name, "path": str(p), "mtime": p.stat().st_mtime} for p in items]

@app.post("/api/versions/{vid}/rollback")
def rollback(vid: str):
    p = VERSIONS_DIR / vid
    if not p.exists():
        raise HTTPException(404, "version not found")
    backup_current()
    shutil.copy2(p, SMB_CONF)
    out = run(["systemctl", "reload", SERVICE])
    return {"ok": out.returncode == 0, "output": (out.stdout or "") + (out.stderr or "")}