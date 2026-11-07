from pathlib import Path

from socialclub_exporter.settings import (
    AppSettings,
    app_data_dir,
    default_settings,
    load_settings,
    save_settings,
)


def test_default_settings_uses_documents(monkeypatch, tmp_path):
    monkeypatch.setenv("SOCIALCLUB_EXPORTER_DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setenv("SOCIALCLUB_EXPORTER_DATA_DIR", str(tmp_path / "data"))
    s = default_settings()
    assert s.output_root == tmp_path / "SocialClubChatExport"
    assert s.proxy_port == 18888
    assert s.target_nickname is None


def test_settings_round_trip(tmp_path):
    p = tmp_path / "settings.json"
    s = AppSettings(output_root=tmp_path / "out", target_nickname="TargetUser")
    save_settings(p, s)
    assert load_settings(p) == s


def test_load_settings_missing_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLUB_EXPORTER_DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setenv("SOCIALCLUB_EXPORTER_DATA_DIR", str(tmp_path / "data"))
    assert load_settings(tmp_path / "missing.json") == default_settings()


def test_app_data_dir_respects_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALCLUB_EXPORTER_DATA_DIR", str(tmp_path / "appdata"))
    assert app_data_dir() == tmp_path / "appdata"
