from __future__ import annotations

from pathlib import Path

import pytest

from aya_afi.utils import paths


def test_get_app_root_dev_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    root = paths.get_app_root()
    assert root.exists()
    assert root.is_dir()


def test_get_app_root_frozen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.setattr(paths.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.get_app_root() == tmp_path


def test_get_app_root_frozen_missing_meipass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.delattr(paths.sys, "_MEIPASS", raising=False)
    with pytest.raises(RuntimeError, match="_MEIPASS"):
        paths.get_app_root()


def _patch_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: cls(home)))


def test_user_dirs_created(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    for getter in (
        paths.get_user_data_dir,
        paths.get_config_dir,
        paths.get_logs_dir,
        paths.get_drafts_dir,
        paths.get_secrets_dir,
    ):
        result = getter()
        assert result.exists()
        assert result.is_dir()


def test_db_path_under_user_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_home(monkeypatch, tmp_path)
    assert paths.get_db_path().parent == paths.get_user_data_dir()
    assert paths.get_db_path().name == "aya_afi.sqlite"
