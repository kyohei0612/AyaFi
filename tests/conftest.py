"""Shared pytest configuration.

Adds ``src/`` to ``sys.path`` so tests can import the package without an editable
install. Harmless when the package is already installed (``pip install -e .``).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
