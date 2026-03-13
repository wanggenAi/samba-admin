from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from time import time


def _cleanup_old_logs(log_dir: Path, base_filename: str, retain_days: int) -> None:
    if retain_days <= 0:
        return
    now = time()
    max_age_seconds = retain_days * 24 * 60 * 60
    pattern = f"{base_filename}*"
    for path in log_dir.glob(pattern):
        if not path.is_file():
            continue
        try:
            age = now - path.stat().st_mtime
        except OSError:
            continue
        if age <= max_age_seconds:
            continue
        try:
            path.unlink()
        except OSError:
            continue


def configure_file_logging(
    *,
    log_dir: Path,
    file_name: str,
    level: str = "INFO",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 20,
    retain_days: int = 7,
) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_old_logs(log_dir=log_dir, base_filename=file_name, retain_days=retain_days)

    root = logging.getLogger()
    marker = "_samba_admin_file_logging"
    if any(getattr(h, marker, False) for h in root.handlers):
        return

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = RotatingFileHandler(
        log_dir / file_name,
        maxBytes=max(1, int(max_bytes)),
        backupCount=max(1, int(backup_count)),
        encoding="utf-8",
    )
    handler.setFormatter(fmt)
    setattr(handler, marker, True)

    root_level = getattr(logging, str(level or "INFO").upper(), logging.INFO)
    root.setLevel(root_level)
    root.addHandler(handler)

    # Ensure uvicorn logs are also persisted to file.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.setLevel(root_level)
        logger.addHandler(handler)
