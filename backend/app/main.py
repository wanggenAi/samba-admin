from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.logging_setup import configure_file_logging
from .core.settings import settings
from .routers import admin, auth, config, ldap, system, users, versions


def create_app() -> FastAPI:
    configure_file_logging(
        log_dir=settings.log_dir,
        file_name=settings.log_file_name,
        level=settings.log_level,
        max_bytes=settings.log_max_bytes,
        backup_count=settings.log_backup_count,
        retain_days=settings.log_retain_days,
    )

    app = FastAPI(
        title="Samba Admin API (AD DC)",
        version="1.0.0",
    )

    cors_origins = settings.cors_origins or ["*"]
    allow_credentials = settings.cors_allow_credentials
    # Browsers reject credentials with wildcard origin.
    if "*" in cors_origins and allow_credentials:
        allow_credentials = False

    # CORS: default permissive for development; configure in production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
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
