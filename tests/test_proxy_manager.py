from socialclub_exporter import proxy_manager as pm


def test_compute_proxy_settings_points_to_local_port():
    current = pm.ProxySettings(
        proxy_enable=0,
        proxy_server="127.0.0.1:7897",
        proxy_override="localhost;127.*;<local>",
        auto_config_url=None,
    )
    result = pm.compute_proxy_settings(current, 18888)
    assert result.proxy_enable == 1
    assert result.proxy_server == "127.0.0.1:18888"
    assert result.auto_config_url is None
    assert "<local>" in result.proxy_override


def test_backup_round_trip_preserves_original_values(tmp_path):
    path = tmp_path / "proxy_backup.json"
    original = pm.ProxySettings(
        proxy_enable=0,
        proxy_server="127.0.0.1:7897",
        proxy_override="localhost;127.*;<local>",
        auto_config_url="http://example.test/proxy.pac",
    )
    pm.save_backup(path, original)
    assert pm.load_backup(path) == original


def test_restore_if_stale_restores_only_when_port_matches(tmp_path, monkeypatch):
    backup = tmp_path / "proxy_backup.json"
    pm.save_backup(
        backup,
        pm.ProxySettings(0, "127.0.0.1:7897", "original", None),
    )
    monkeypatch.setattr(
        pm,
        "read_proxy_settings",
        lambda: pm.ProxySettings(1, "127.0.0.1:18888", "<local>", None),
    )
    restored = []
    monkeypatch.setattr(pm, "restore_proxy", lambda path: restored.append(path) or True)

    assert pm.restore_if_stale(backup, 18888) is True
    assert restored == [backup]


def test_restore_if_stale_ignores_other_proxy(tmp_path, monkeypatch):
    backup = tmp_path / "proxy_backup.json"
    pm.save_backup(
        backup,
        pm.ProxySettings(0, "127.0.0.1:7897", "original", None),
    )
    monkeypatch.setattr(
        pm,
        "read_proxy_settings",
        lambda: pm.ProxySettings(1, "127.0.0.1:9999", "<local>", None),
    )
    restored = []
    monkeypatch.setattr(pm, "restore_proxy", lambda path: restored.append(path) or True)

    assert pm.restore_if_stale(backup, 18888) is False
    assert restored == []


def test_restore_if_stale_accepts_any_loopback_for_random_ports(
    tmp_path, monkeypatch
):
    backup = tmp_path / "proxy_backup.json"
    pm.save_backup(
        backup,
        pm.ProxySettings(0, "127.0.0.1:7897", "original", None),
    )
    monkeypatch.setattr(
        pm,
        "read_proxy_settings",
        lambda: pm.ProxySettings(1, "127.0.0.1:51234", "<local>", None),
    )
    restored = []
    monkeypatch.setattr(pm, "restore_proxy", lambda path: restored.append(path) or True)

    assert pm.restore_if_stale(backup) is True
    assert restored == [backup]
