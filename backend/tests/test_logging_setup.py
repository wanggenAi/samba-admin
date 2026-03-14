from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.core.logging_setup import _cleanup_old_logs, configure_file_logging


class _FakePath:
    def __init__(self, *, is_file=True, mtime=0, stat_raises=False, unlink_raises=False):
        self._is_file = is_file
        self._mtime = mtime
        self._stat_raises = stat_raises
        self._unlink_raises = unlink_raises
        self.deleted = False

    def is_file(self):
        return self._is_file

    def stat(self):
        if self._stat_raises:
            raise OSError("stat error")
        return SimpleNamespace(st_mtime=self._mtime)

    def unlink(self):
        if self._unlink_raises:
            raise OSError("unlink error")
        self.deleted = True


class _FakeLogger:
    def __init__(self):
        self.handlers = []
        self.level = None

    def setLevel(self, level):
        self.level = level

    def addHandler(self, handler):
        self.handlers.append(handler)


class _FakeHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.formatter = None

    def setFormatter(self, fmt):
        self.formatter = fmt


class LoggingSetupTests(unittest.TestCase):
    def test_cleanup_old_logs_branches(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            log_dir = Path(td)
            # retain_days <= 0 short-circuit
            _cleanup_old_logs(log_dir, "backend.log", 0)

            old = _FakePath(is_file=True, mtime=0)
            new = _FakePath(is_file=True, mtime=999_999_999)
            not_file = _FakePath(is_file=False)
            stat_fail = _FakePath(stat_raises=True)
            unlink_fail = _FakePath(is_file=True, mtime=0, unlink_raises=True)

            with patch("app.core.logging_setup.time", return_value=1_000_000_000):
                with patch("pathlib.Path.glob", return_value=[old, new, not_file, stat_fail, unlink_fail]):
                    _cleanup_old_logs(log_dir, "backend.log", 1)

            self.assertTrue(old.deleted)
            self.assertFalse(new.deleted)

    def test_configure_file_logging_idempotent_and_setup(self) -> None:
        root = _FakeLogger()
        existing = _FakeHandler()
        setattr(existing, "_samba_admin_file_logging", True)
        root.handlers.append(existing)

        with tempfile.TemporaryDirectory() as td:
            log_dir = Path(td)

            # idempotent early return when marker exists
            with patch("app.core.logging_setup.logging.getLogger", return_value=root):
                configure_file_logging(log_dir=log_dir, file_name="backend.log")
            self.assertEqual(len(root.handlers), 1)

            root = _FakeLogger()
            uvicorn = _FakeLogger()
            uvicorn_error = _FakeLogger()
            uvicorn_access = _FakeLogger()
            loggers = {
                "": root,
                "uvicorn": uvicorn,
                "uvicorn.error": uvicorn_error,
                "uvicorn.access": uvicorn_access,
            }

            def _get_logger(name=""):
                return loggers.get(name, _FakeLogger())

            fake_handler = _FakeHandler()
            with patch("app.core.logging_setup._cleanup_old_logs") as cleanup:
                with patch("app.core.logging_setup.logging.getLogger", side_effect=_get_logger):
                    with patch("app.core.logging_setup.RotatingFileHandler", return_value=fake_handler):
                        configure_file_logging(
                            log_dir=log_dir,
                            file_name="backend.log",
                            level="warning",
                            max_bytes=0,
                            backup_count=0,
                            retain_days=7,
                        )

            cleanup.assert_called_once()
            self.assertEqual(root.level, logging.WARNING)
            self.assertEqual(len(root.handlers), 1)
            self.assertEqual(len(uvicorn.handlers), 1)
            self.assertEqual(len(uvicorn_error.handlers), 1)
            self.assertEqual(len(uvicorn_access.handlers), 1)


if __name__ == "__main__":
    unittest.main()
