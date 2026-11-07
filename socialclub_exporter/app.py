import atexit

from .capture_engine import CaptureEngine
from .cert_manager import CertManager
from .controller import ExportController
from .exporter import export_conversation
from .gui import ExporterApp
from .proxy_manager import ProxyManager
from .settings import app_data_dir, load_settings


def main() -> int:
    data_dir = app_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    settings_path = data_dir / "settings.json"
    settings = load_settings(settings_path)

    cert = CertManager(data_dir / "mitmproxy")
    proxy = ProxyManager(data_dir / "proxy_backup.json")

    try:
        proxy.restore_if_stale()
    except Exception:
        pass

    def capture_factory(port, confdir, event_queue):
        return CaptureEngine(port, confdir, event_queue)

    def export_fn(conversation, output_root, template_path):
        return export_conversation(
            conversation, output_root, template_path
        )

    controller = ExportController(
        settings,
        cert,
        proxy,
        capture_factory,
        export_fn,
    )
    app = ExporterApp(controller, settings_path)
    atexit.register(controller.close)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
