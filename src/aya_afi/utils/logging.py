"""Structured logging setup.

Conforms to engineering constitution rule 6 (stdlib ``logging`` only, structured
JSON formatter) and rule 10 (secrets must never leak into logs).

See: docs/decisions/008-logging-strategy.md.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import Iterable
from logging.handlers import TimedRotatingFileHandler

from pythonjsonlogger.json import JsonFormatter

from aya_afi.utils.paths import get_logs_dir

_LOG_FILENAME = "app.log"
_BACKUP_DAYS = 30
_FIELD_FMT = "%(asctime)s %(levelname)s %(name)s %(event)s %(message)s"
_REDACTION_MARKER = "***REDACTED***"
_SENSITIVE_SUFFIXES = ("_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_API_KEY")


class SecretRedactionFilter(logging.Filter):
    """Replace configured secret values anywhere in a log record with a marker.

    The filter is best-effort: it inspects ``record.msg``, ``record.args``, and
    any string attributes on the record (``extra=...`` fields).
    """

    def __init__(self, values: Iterable[str]) -> None:
        super().__init__()
        patterns = [re.escape(v) for v in values if v]
        self._regex: re.Pattern[str] | None = re.compile("|".join(patterns)) if patterns else None

    def filter(self, record: logging.LogRecord) -> bool:
        if self._regex is None:
            return True
        regex = self._regex
        if isinstance(record.msg, str):
            record.msg = regex.sub(_REDACTION_MARKER, record.msg)
        if record.args:
            record.args = tuple(
                regex.sub(_REDACTION_MARKER, a) if isinstance(a, str) else a
                for a in (record.args if isinstance(record.args, tuple) else ())
            )
        for key, value in list(record.__dict__.items()):
            if isinstance(value, str) and regex.search(value):
                setattr(record, key, regex.sub(_REDACTION_MARKER, value))
        return True


def _collect_secret_values() -> list[str]:
    """Return values from env vars whose names look sensitive."""
    return [v for k, v in os.environ.items() if k.upper().endswith(_SENSITIVE_SUFFIXES) and v]


def setup_logging(level: str = "INFO", *, to_console: bool | None = None) -> None:
    """Configure the root logger. Idempotent (safe to call more than once).

    :param level: Log level name (DEBUG / INFO / WARNING / ERROR).
    :param to_console: Force stderr output on/off. Default: auto-detect TTY.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(level.upper())

    formatter = JsonFormatter(
        _FIELD_FMT,
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    )

    log_path = get_logs_dir() / _LOG_FILENAME
    file_handler = TimedRotatingFileHandler(
        filename=log_path,
        when="midnight",
        backupCount=_BACKUP_DAYS,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(SecretRedactionFilter(_collect_secret_values()))
    root.addHandler(file_handler)

    if to_console is None:
        to_console = sys.stderr.isatty()
    if to_console:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        stream.addFilter(SecretRedactionFilter(_collect_secret_values()))
        root.addHandler(stream)
