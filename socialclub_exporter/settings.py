import json
import os
import sys
import winreg
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    output_root: Path
    target_nickname: str | None = None
    proxy_port: int = 18888
    upstream_proxy: str | None = None


def app_data_dir() -> Path:
    override = os.environ.get("SOCIALCLUB_EXPORTER_DATA_DIR")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "SocialClubChatExporter"
    return Path.home() / "AppData" / "Roaming" / "SocialClubChatExporter"


def documents_dir() -> Path:
    override = os.environ.get("SOCIALCLUB_EXPORTER_DOCUMENTS_DIR")
    if override:
        return Path(override)
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "Personal")
            expanded = os.path.expandvars(str(value))
            if expanded:
                return Path(expanded)
    except OSError:
        pass
    return Path.home() / "Documents"


def default_settings() -> AppSettings:
    return AppSettings(output_root=documents_dir() / "SocialClubChatExport")


def save_settings(path: Path, settings: AppSettings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(settings)
    data["output_root"] = str(settings.output_root)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_settings(path: Path) -> AppSettings:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return AppSettings(
            output_root=Path(raw["output_root"]),
            target_nickname=raw.get("target_nickname"),
            proxy_port=int(raw.get("proxy_port", 18888)),
            upstream_proxy=raw.get("upstream_proxy"),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return default_settings()


def resource_path(relative: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / relative
    return Path(__file__).resolve().parent / relative
