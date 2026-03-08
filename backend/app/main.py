from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import system, config, versions, ldap, users


def create_app() -> FastAPI:
    app = FastAPI(
        title="Samba Admin API (AD DC)",
        version="1.0.0",
    )

    # CORS：开发阶段允许前端访问（生产再收紧）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(system.router, prefix="/api/system", tags=["system"])
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(versions.router, prefix="/api/versions", tags=["versions"])
    app.include_router(ldap.router, prefix="/api/ldap", tags=["ldap"])
    app.include_router(users.router, prefix="/api/users", tags=["users"])

    @app.get("/health")
    def health():
        return {"ok": True, "mode": "ad-dc"}

    return app


app = create_app()