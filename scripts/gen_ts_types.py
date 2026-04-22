"""Regenerate TypeScript IPC type definitions from pydantic models.

Single source of truth: ``src/aya_afi/ipc/protocol.py`` (pydantic).
Output: ``ui/src/types/generated/ipc.ts``.

Stage 0 status: the protocol module does not exist yet. This script is a no-op
placeholder until ADR-003 is implemented in Stage 1.

See: docs/decisions/003-ipc-protocol.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = ROOT / "src" / "aya_afi" / "ipc" / "protocol.py"
OUT = ROOT / "ui" / "src" / "types" / "generated" / "ipc.ts"


def main() -> int:
    if not PROTOCOL.exists():
        print(f"[gen_ts_types] {PROTOCOL} not found - skipping (Stage 0 placeholder).")
        return 0
    raise NotImplementedError("Wire up datamodel-code-generator here in Stage 1 (ADR-003).")


if __name__ == "__main__":
    sys.exit(main())
