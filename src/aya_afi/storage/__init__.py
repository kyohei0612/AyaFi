"""SQLite-backed persistence layer.

See: docs/decisions/005-post-history-and-integrity.md (投稿履歴 + 整合性).

Synchronous SQLAlchemy 2.x for simplicity; async IPC handlers wrap calls
with ``asyncio.to_thread`` when needed (Stage 5.b wiring).
"""
