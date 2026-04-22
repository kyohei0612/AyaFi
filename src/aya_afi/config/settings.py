"""Runtime settings loaded from ``secrets/.env`` + environment variables.

Used as a single source of truth for which LLM provider to use, API keys,
and related runtime knobs. Conforms to engineering constitution rule 4
(no hard-coded paths/URLs/thresholds).

In dev: reads ``<repo>/secrets/.env``.
In frozen: reads ``%APPDATA%/aya-afi/secrets/.env``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from aya_afi.utils.paths import get_app_root, get_secrets_dir, is_frozen

LlmProviderName = Literal["mock", "gemini"]


def _default_env_file() -> Path:
    if is_frozen():
        return get_secrets_dir() / ".env"
    return get_app_root() / "secrets" / ".env"


class Settings(BaseSettings):
    """Top-level application settings.

    Env var names are case-insensitive. Unknown keys are ignored so users can
    keep extra entries in ``.env`` without breaking the app.
    """

    model_config = SettingsConfigDict(
        env_file=str(_default_env_file()),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM selection ---
    llm_provider: LlmProviderName = Field(
        default="mock",
        description=(
            "Which LLM to call. 'mock' returns deterministic canned text "
            "(no network, no key). 'gemini' requires GEMINI_API_KEY."
        ),
    )
    llm_model: str | None = Field(
        default=None,
        description="Override model name; falls back to provider default.",
    )

    # --- API keys ---
    gemini_api_key: str | None = Field(default=None)
    # Secondary Gemini key used when the primary hits transient errors
    # (503 UNAVAILABLE / rate limit). Leave empty if only one key is available.
    gemini_api_key_fallback: str | None = Field(default=None)
    anthropic_api_key: str | None = Field(default=None)

    # --- Affiliate (Rakuten direct) ---
    rakuten_application_id: str | None = Field(
        default=None,
        description="Rakuten Web Service アプリ ID (https://webservice.rakuten.co.jp/)",
    )
    rakuten_affiliate_id: str | None = Field(
        default=None, description="Rakuten Affiliate ID for click tracking."
    )

    # --- Affiliate (moshimo for Amazon) ---
    moshimo_a_id: str | None = Field(
        default=None,
        description="もしもアフィリエイト会員 ID (a_id) 共通キー",
    )
    moshimo_amazon_p_id: str | None = Field(default=None)
    moshimo_amazon_pc_id: str | None = Field(default=None)
    moshimo_amazon_pl_id: str | None = Field(default=None)

    # --- SNS posting (Stage 3) ---
    threads_access_token: str | None = Field(default=None)
    threads_user_id: str | None = Field(default=None)
    bluesky_handle: str | None = Field(default=None)
    bluesky_app_password: str | None = Field(default=None)

    # --- Runtime toggles ---
    dry_run: bool = Field(
        default=False,
        description="If True, posting flows log what would happen but skip real API calls.",
    )
    affiliate_force_mock: bool = Field(
        default=False,
        description=(
            "If True, the affiliate factory always returns the mock provider "
            "regardless of URL. Useful for offline dev / CI."
        ),
    )
    log_level: str = Field(default="INFO")
