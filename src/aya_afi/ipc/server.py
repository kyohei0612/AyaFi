"""Async NDJSON IPC server over stdin/stdout.

Reads one JSON ``Request`` per line from stdin, dispatches to a registered
handler, and writes a ``Response`` line to stdout. Also emits periodic
``Event`` (heartbeat) messages so the Tauri side can detect a silent death.

Test ergonomics: ``IpcServer.handle_line(raw)`` is directly callable without
any actual stdin/stdout plumbing; tests inject a writer callable.

See: docs/decisions/003-ipc-protocol.md.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from collections.abc import Callable
from typing import IO

from pydantic import ValidationError

from aya_afi.affiliate.errors import (
    AffiliateAPIError,
    AffiliateConfigError,
    InvalidUrlError,
    ProductNotFoundError,
    UnsupportedUrlError,
)
from aya_afi.config.settings import Settings
from aya_afi.ipc.handlers import (
    HandlerFn,
    handle_health_check,
    handle_ping,
    handle_validate_content,
    make_fetch_product_handler,
    make_generate_post_handler,
)
from aya_afi.ipc.protocol import (
    SCHEMA_VERSION,
    UNKNOWN_REQUEST_ID,
    ErrorInfo,
    Event,
    EventType,
    Request,
    RequestAction,
    Response,
)
from aya_afi.llm.errors import (
    LLMAPIError,
    LLMQuotaExceededError,
    LLMRateLimitError,
    LLMValidationError,
)
from aya_afi.llm.factory import create_provider
from aya_afi.utils.logging import setup_logging

WriterFn = Callable[[str], None]

HEARTBEAT_INTERVAL_SEC = 10.0


class IpcServer:
    """Request dispatcher. Stateless per-message; tests use ``handle_line`` directly."""

    def __init__(self, writer: WriterFn | None = None) -> None:
        self._handlers: dict[RequestAction, HandlerFn] = {}
        self._log = logging.getLogger("aya_afi.ipc.server")
        self._writer: WriterFn = writer or _stdout_writer
        self._pending_tasks: set[asyncio.Task[None]] = set()

    def register(self, action: RequestAction, handler: HandlerFn) -> None:
        self._handlers[action] = handler

    def _emit(self, payload: Response | Event) -> None:
        self._writer(payload.model_dump_json(exclude_none=True))

    async def handle_line(self, line: str) -> None:
        """Process one raw JSON line and emit exactly one Response (on non-blank input)."""
        stripped = line.strip()
        if not stripped:
            return
        try:
            req = Request.model_validate_json(stripped)
        except ValidationError as e:
            self._emit(
                Response(
                    request_id=UNKNOWN_REQUEST_ID,
                    ok=False,
                    error=ErrorInfo(type="parse", message=str(e)),
                )
            )
            return

        handler = self._handlers.get(req.action)
        if handler is None:
            self._emit(
                Response(
                    request_id=req.request_id,
                    ok=False,
                    error=ErrorInfo(
                        type="unknown_action",
                        message=f"no handler registered for {req.action.value}",
                    ),
                )
            )
            return

        try:
            data = await asyncio.wait_for(handler(req), timeout=req.timeout_sec)
        except TimeoutError:
            self._emit(
                Response(
                    request_id=req.request_id,
                    ok=False,
                    error=ErrorInfo(
                        type="timeout",
                        message=f"handler exceeded {req.timeout_sec}s",
                    ),
                )
            )
            return
        except Exception as e:
            # Top-level boundary: classify and emit a structured error response.
            self._log.exception(
                "ipc_handler_error",
                extra={"event": "ipc_handler_error", "action": req.action.value},
            )
            self._emit(
                Response(
                    request_id=req.request_id,
                    ok=False,
                    error=_classify_exception(e),
                )
            )
            return

        self._emit(Response(request_id=req.request_id, ok=True, data=data))

    async def _read_stdin_loop(self, stdin: IO[str]) -> None:
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, stdin.readline)
            if not line:  # EOF
                return
            task = asyncio.create_task(self.handle_line(line))
            self._pending_tasks.add(task)
            task.add_done_callback(self._pending_tasks.discard)

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SEC)
            self._emit(Event(event_type=EventType.heartbeat))

    async def run(self, stdin: IO[str] | None = None) -> None:
        """Emit ``sidecar_ready`` and loop until stdin EOF."""
        self._emit(Event(event_type=EventType.sidecar_ready))
        self._log.info(
            "sidecar_ready",
            extra={"event": "sidecar_ready", "protocol_version": SCHEMA_VERSION},
        )
        reader = asyncio.create_task(self._read_stdin_loop(stdin or sys.stdin))
        heartbeat = asyncio.create_task(self._heartbeat_loop())
        try:
            await reader
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
            # Drain in-flight handler tasks so EOF doesn't kill slow LLM calls
            # mid-flight (important for CLI smoke tests that feed a single line
            # then close stdin).
            if self._pending_tasks:
                await asyncio.gather(*self._pending_tasks, return_exceptions=True)


def _classify_exception(e: Exception) -> ErrorInfo:
    """Map an exception to a stable ``ErrorInfo.type`` value."""
    if isinstance(e, ValidationError | LLMValidationError):
        return ErrorInfo(type="validation", message=str(e))
    if isinstance(e, LLMRateLimitError):
        return ErrorInfo(
            type="rate_limit",
            message=str(e),
            retry_after_sec=e.retry_after_sec,
        )
    if isinstance(e, LLMQuotaExceededError):
        return ErrorInfo(type="llm_quota_exceeded", message=str(e))
    if isinstance(e, UnsupportedUrlError):
        return ErrorInfo(type="unsupported_url", message=str(e))
    if isinstance(e, InvalidUrlError):
        return ErrorInfo(type="invalid_url", message=str(e))
    if isinstance(e, ProductNotFoundError):
        return ErrorInfo(type="product_not_found", message=str(e))
    if isinstance(e, AffiliateConfigError):
        return ErrorInfo(type="affiliate_config", message=str(e))
    if isinstance(e, AffiliateAPIError | LLMAPIError):
        return ErrorInfo(type="api_down", message=str(e))
    return ErrorInfo(type="internal", message=str(e))


def _stdout_writer(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def main() -> int:
    """Entry point for ``scripts/sidecar.py``. Wires Settings → LLM → handlers."""
    # Force UTF-8 on stdin/stdout regardless of Windows system codepage.
    # Without this, Japanese characters get corrupted by cp932.
    sys.stdin.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    settings = Settings()
    setup_logging(level=settings.log_level, to_console=False)
    log = logging.getLogger("aya_afi.ipc.server")
    log.info(
        "settings_loaded",
        extra={
            "event": "settings_loaded",
            "llm_provider": settings.llm_provider,
            "dry_run": settings.dry_run,
        },
    )

    llm = create_provider(
        settings.llm_provider,
        api_key=settings.gemini_api_key,
        model=settings.llm_model,
        fallback_api_key=settings.gemini_api_key_fallback,
    )
    log.info(
        "llm_provider_ready",
        extra={"event": "llm_provider_ready", "provider": llm.name},
    )

    server = IpcServer()
    server.register(RequestAction.ping, handle_ping)
    server.register(RequestAction.health_check, handle_health_check)
    server.register(RequestAction.fetch_product, make_fetch_product_handler(settings))
    server.register(RequestAction.generate_post, make_generate_post_handler(llm))
    server.register(RequestAction.validate_content, handle_validate_content)

    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        pass
    return 0
