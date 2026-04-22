from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from aya_afi.config.settings import Settings


def test_defaults_without_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DRY_RUN", raising=False)
    missing = tmp_path / ".no-such.env"
    s = Settings(_env_file=str(missing))
    assert s.llm_provider == "mock"
    assert s.gemini_api_key is None
    assert s.dry_run is False
    assert s.log_level == "INFO"


def test_reads_from_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "LLM_PROVIDER=gemini\n" "GEMINI_API_KEY=sk-from-file\n" "DRY_RUN=true\n",
        encoding="utf-8",
    )
    s = Settings(_env_file=str(env))
    assert s.llm_provider == "gemini"
    assert s.gemini_api_key == "sk-from-file"
    assert s.dry_run is True


def test_env_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    s = Settings(_env_file=str(env))
    assert s.gemini_api_key == "from-env"


def test_unknown_keys_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=x\nFUTURE_FEATURE_TOGGLE=on\n", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    # Should not raise even though FUTURE_FEATURE_TOGGLE has no matching field.
    Settings(_env_file=str(env))


def test_invalid_provider_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "cohere")
    missing = tmp_path / ".no-such.env"
    with pytest.raises(ValidationError):
        Settings(_env_file=str(missing))


def test_affiliate_fields_default_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for k in (
        "RAKUTEN_APPLICATION_ID",
        "RAKUTEN_AFFILIATE_ID",
        "MOSHIMO_A_ID",
        "MOSHIMO_AMAZON_P_ID",
        "MOSHIMO_AMAZON_PC_ID",
        "MOSHIMO_AMAZON_PL_ID",
        "AFFILIATE_FORCE_MOCK",
    ):
        monkeypatch.delenv(k, raising=False)
    missing = tmp_path / ".no-such.env"
    s = Settings(_env_file=str(missing))
    assert s.rakuten_application_id is None
    assert s.moshimo_a_id is None
    assert s.affiliate_force_mock is False


def test_affiliate_fields_read_from_env_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "RAKUTEN_APPLICATION_ID=rakuten-app\n"
        "RAKUTEN_AFFILIATE_ID=rakuten-aff\n"
        "MOSHIMO_A_ID=moshimo-a\n"
        "MOSHIMO_AMAZON_P_ID=moshimo-p\n"
        "MOSHIMO_AMAZON_PC_ID=moshimo-pc\n"
        "MOSHIMO_AMAZON_PL_ID=moshimo-pl\n"
        "AFFILIATE_FORCE_MOCK=true\n",
        encoding="utf-8",
    )
    s = Settings(_env_file=str(env))
    assert s.rakuten_application_id == "rakuten-app"
    assert s.rakuten_affiliate_id == "rakuten-aff"
    assert s.moshimo_a_id == "moshimo-a"
    assert s.moshimo_amazon_p_id == "moshimo-p"
    assert s.affiliate_force_mock is True
