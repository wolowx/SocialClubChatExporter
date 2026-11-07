import ctypes
import json
import socket
import winreg
from dataclasses import asdict, dataclass
from pathlib import Path

_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"


@dataclass(frozen=True)
class ProxySettings:
    proxy_enable: int
    proxy_server: str
    proxy_override: str
    auto_config_url: str | None


def allocate_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def compute_proxy_settings(current: ProxySettings, port: int) -> ProxySettings:
    return ProxySettings(
        proxy_enable=1,
        proxy_server=f"127.0.0.1:{port}",
        proxy_override="<local>;127.0.0.1;localhost",
        auto_config_url=None,
    )


def read_proxy_settings() -> ProxySettings:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as key:
        def value(name: str, default):
            try:
                result, _ = winreg.QueryValueEx(key, name)
                return result
            except FileNotFoundError:
                return default

        auto_config = value("AutoConfigURL", "")
        return ProxySettings(
            proxy_enable=int(value("ProxyEnable", 0)),
            proxy_server=str(value("ProxyServer", "")),
            proxy_override=str(value("ProxyOverride", "")),
            auto_config_url=str(auto_config) or None,
        )


def notify_proxy_change() -> None:
    try:
        wininet = ctypes.windll.wininet
        wininet.InternetSetOptionW(None, 39, None, 0)
        wininet.InternetSetOptionW(None, 37, None, 0)
    except Exception:
        pass


def apply_proxy_settings(settings: ProxySettings) -> None:
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        _REG_PATH,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(
            key, "ProxyEnable", 0, winreg.REG_DWORD, int(settings.proxy_enable)
        )
        winreg.SetValueEx(
            key, "ProxyServer", 0, winreg.REG_SZ, settings.proxy_server
        )
        winreg.SetValueEx(
            key, "ProxyOverride", 0, winreg.REG_SZ, settings.proxy_override
        )
        if settings.auto_config_url:
            winreg.SetValueEx(
                key, "AutoConfigURL", 0, winreg.REG_SZ, settings.auto_config_url
            )
        else:
            try:
                winreg.DeleteValue(key, "AutoConfigURL")
            except FileNotFoundError:
                pass
    notify_proxy_change()


def save_backup(path: Path, settings: ProxySettings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_backup(path: Path) -> ProxySettings:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ProxySettings(
        proxy_enable=int(raw["proxy_enable"]),
        proxy_server=str(raw["proxy_server"]),
        proxy_override=str(raw["proxy_override"]),
        auto_config_url=raw.get("auto_config_url") or None,
    )


def set_local_proxy(port: int, backup_path: Path) -> ProxySettings:
    current = read_proxy_settings()
    save_backup(backup_path, current)
    apply_proxy_settings(compute_proxy_settings(current, port))
    return current


def restore_proxy(backup_path: Path) -> bool:
    if not backup_path.exists():
        return False
    backup = load_backup(backup_path)
    apply_proxy_settings(backup)
    backup_path.unlink(missing_ok=True)
    return True


def restore_if_stale(backup_path: Path, port: int | None = None) -> bool:
    if not backup_path.exists():
        return False
    current = read_proxy_settings()
    if current.proxy_enable != 1:
        return False
    if port is None:
        if current.proxy_server.startswith("127.0.0.1:"):
            return restore_proxy(backup_path)
        return False
    if current.proxy_server == f"127.0.0.1:{port}":
        return restore_proxy(backup_path)
    return False


class ProxyManager:
    def __init__(self, backup_path: Path):
        self.backup_path = Path(backup_path)

    def set_local(self, port: int) -> ProxySettings:
        return set_local_proxy(port, self.backup_path)

    def restore(self) -> bool:
        return restore_proxy(self.backup_path)

    def restore_if_stale(self, port: int | None = None) -> bool:
        return restore_if_stale(self.backup_path, port)
