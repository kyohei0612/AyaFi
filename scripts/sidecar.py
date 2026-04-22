"""Tauri から spawn される Python sidecar のエントリポイント (最薄)。

処理は ``src/aya_afi/ipc/server.py`` に委譲する
(プロチェック rule 1: ``scripts/`` = CLI エントリのみ、ロジックは ``src/``)。
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    """Allow running without ``pip install -e .`` during development."""
    root = Path(__file__).resolve().parent.parent
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def main() -> int:
    _ensure_src_on_path()
    from aya_afi.ipc import server

    return server.main()


if __name__ == "__main__":
    sys.exit(main())
