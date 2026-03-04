from fastapi import FastAPI
from pathlib import Path
from fastapi.staticfiles import StaticFiles

from .routers import system, config, versions

app = FastAPI(
    title="Samba Admin API",
    version="1.0.0"
)

# 注册路由
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(config.router, prefix="/api/config", tags=["config"])
app.include_router(versions.router, prefix="/api/versions", tags=["versions"])


# ===== 静态前端 (dist) =====

APP_DIR = Path(__file__).resolve().parent
DIST_DIR = APP_DIR.parent / "dist"

if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="frontend")