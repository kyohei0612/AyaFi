"""CLI フォールバック (Tauri UI が動かない場合のコマンドライン実行モード)。

Stage 0 ではプレースホルダ。Stage 1 以降で実装 (ADR-001 ロールバック手順参照)。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    root = Path(__file__).resolve().parent.parent
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def main() -> int:
    _ensure_src_on_path()
    from aya_afi.utils.logging import setup_logging

    setup_logging(level="INFO", to_console=True)
    log = logging.getLogger("cli")
    log.info("cli_not_implemented_yet", extra={"event": "cli_placeholder"})
    sys.stderr.write("aya-afi CLI is not implemented yet (Stage 0 placeholder).\n")
    sys.stderr.write("See docs/decisions/ for planned functionality.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
