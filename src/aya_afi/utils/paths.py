"""Cross-environment path resolution for dev and PyInstaller frozen builds.

All path access in the sidecar MUST go through this module. Hardcoded absolute
paths are forbidden by the engineering constitution (rule 4).

See: docs/decisions/001-initial-architecture.md (Revisions 2026-04-22).
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = "aya-afi"


def is_frozen() -> bool:
    """Return True if running from a PyInstaller-built executable."""
    return getattr(sys, "frozen", False)


def get_app_root() -> Path:
    """Base of read-only bundled resources.

    - dev: repository root (four levels above this file).
    - frozen: PyInstaller's temporary extraction directory (``sys._MEIPASS``).
    """
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass is None:
            raise RuntimeError("sys.frozen is True but sys._MEIPASS is unset")
        return Path(meipass)
    return Path(__file__).resolve().parents[3]


def get_user_data_dir() -> Path:
    """Writable user data root (``%APPDATA%\\aya-afi`` on Windows).

    Created on demand.
    """
    base = Path.home() / "AppData" / "Roaming" / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_default_config_dir() -> Path:
    """Read-only default config shipped with the app (for 2-layer config)."""
    return get_app_root() / "config"


def get_config_dir() -> Path:
    """User-editable config directory (overrides defaults)."""
    path = get_user_data_dir() / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_logs_dir() -> Path:
    """Directory for rotated log files."""
    path = get_user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_drafts_dir() -> Path:
    """Directory for auto-saved draft markdown files."""
    path = get_user_data_dir() / "drafts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_secrets_dir() -> Path:
    """Directory for the user's .env and token files."""
    path = get_user_data_dir() / "secrets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_db_path() -> Path:
    """Absolute path to the SQLite database file (not created here)."""
    return get_user_data_dir() / "aya_afi.sqlite"


def get_alembic_dir() -> Path:
    """Alembic migration scripts (bundled, read-only)."""
    return get_app_root() / "alembic"
