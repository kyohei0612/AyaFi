from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from aya_afi.utils import logging as aya_logging


def _read_last_log_line(path: Path) -> dict[str, object]:
    content = path.read_text(encoding="utf-8").strip()
    assert content, f"no log content at {path}"
    return json.loads(content.splitlines()[-1])


def test_setup_writes_json_to_logs_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(aya_logging, "get_logs_dir", lambda: tmp_path)
    aya_logging.setup_logging(level="INFO", to_console=False)

    logger = logging.getLogger("aya.test.json")
    logger.info("hello world", extra={"event": "unit_test"})
    for handler in logging.getLogger().handlers:
        handler.flush()

    record = _read_last_log_line(tmp_path / "app.log")
    assert record["event"] == "unit_test"
    assert record["message"] == "hello world"
    assert record["level"] == "INFO"


def test_secret_redaction(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-abc123")
    monkeypatch.setattr(aya_logging, "get_logs_dir", lambda: tmp_path)
    aya_logging.setup_logging(level="INFO", to_console=False)

    logger = logging.getLogger("aya.test.redact")
    logger.info("token=%s", "super-secret-abc123", extra={"event": "redact_check"})
    for handler in logging.getLogger().handlers:
        handler.flush()

    content = (tmp_path / "app.log").read_text(encoding="utf-8")
    assert "super-secret-abc123" not in content
    assert "***REDACTED***" in content


def test_setup_is_idempotent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(aya_logging, "get_logs_dir", lambda: tmp_path)
    aya_logging.setup_logging(level="INFO", to_console=False)
    first_handler_count = len(logging.getLogger().handlers)
    aya_logging.setup_logging(level="INFO", to_console=False)
    second_handler_count = len(logging.getLogger().handlers)
    assert first_handler_count == second_handler_count
