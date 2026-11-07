from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")

from socialclub_exporter.cert_manager import CertStatus
from socialclub_exporter.controller import ControllerState
from socialclub_exporter.gui import ExporterApp
from socialclub_exporter.settings import AppSettings


class FakeController:
    def __init__(self, installed=True):
        self.settings = AppSettings(output_root=Path("out"))
        self.callbacks = None
        self.closed = False
        self.started = False
        self.installed = installed
        self.install_calls = 0
        self.stop_calls = 0
        self.abort_calls = 0
        self.target_nickname = "TargetUser"
        self.state = ControllerState.IDLE
        self.pages = []

    def certificate_status(self):
        return CertStatus(Path("cert.cer"), "thumb", self.installed)

    def install_certificate(self):
        self.installed = True
        self.install_calls += 1
        return self.certificate_status()

    def uninstall_certificate(self):
        self.installed = False

    def start_capture(self):
        self.started = True

    def poll_capture_events(self):
        return []

    def stop_and_export(self, force=False):
        self.stop_calls += 1
        raise AssertionError("stop_and_export should not be called here")

    def abort_capture(self, message):
        self.abort_calls += 1

    def close(self):
        self.closed = True


def test_app_constructs_and_closes(tmp_path):
    try:
        app = ExporterApp(FakeController(), tmp_path / "settings.json")
    except tk.TclError:
        pytest.skip("no display available")

    app.withdraw()
    app.update()
    assert app.title() == "Social Club 聊天导出器"
    controller = app.controller
    app._on_close()
    assert controller.closed is True


def make_app(controller, tmp_path):
    try:
        app = ExporterApp(controller, tmp_path / "settings.json")
    except tk.TclError:
        pytest.skip("no display available")
    app.withdraw()
    app.update()
    return app


def test_progress_shows_has_more(tmp_path):
    app = make_app(FakeController(), tmp_path)
    app._on_progress(1, 5, 10, False)
    assert "已到最早消息" in app.count_var.get()
    app._on_progress(1, 5, 10, True)
    assert "仍有更多" in app.count_var.get()
    app._on_progress(1, 5, None, None)
    assert "未知" in app.count_var.get()
    app._on_close()


def test_certificate_install_does_not_auto_start(tmp_path, monkeypatch):
    controller = FakeController(installed=False)
    app = make_app(controller, tmp_path)
    monkeypatch.setattr(
        "socialclub_exporter.gui.messagebox.askyesno", lambda *a, **k: True
    )
    monkeypatch.setattr(
        "socialclub_exporter.gui.messagebox.showinfo", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "socialclub_exporter.gui.messagebox.showerror", lambda *a, **k: None
    )

    app._on_start()

    assert controller.install_calls == 1
    assert controller.started is False
    app._on_close()


def test_empty_target_requires_confirmation(tmp_path, monkeypatch):
    controller = FakeController()
    app = make_app(controller, tmp_path)
    app.target_var.set("")
    monkeypatch.setattr(
        "socialclub_exporter.gui.messagebox.askyesno", lambda *a, **k: False
    )

    app._on_stop()

    assert controller.stop_calls == 0
    app._on_close()


def test_timeout_aborts_when_waiting(tmp_path):
    controller = FakeController()
    controller.state = ControllerState.WAITING
    app = make_app(controller, tmp_path)

    app._on_capture_timeout()

    assert controller.abort_calls == 1
    app._on_close()


def test_waiting_status_resets_timeout(tmp_path):
    controller = FakeController()
    controller.state = ControllerState.WAITING
    app = make_app(controller, tmp_path)
    app._timeout_id = app.after(60000, lambda: None)
    first = app._timeout_id

    app._on_status("已忽略会话，等待目标昵称")

    assert app._timeout_id != first
    app._cancel_timeout()
    app._on_close()


def test_gui_has_no_log_widget(tmp_path):
    app = make_app(FakeController(), tmp_path)
    assert not hasattr(app, "log")
    app._on_close()


def test_log_writes_to_file(tmp_path):
    app = make_app(FakeController(), tmp_path)
    app._on_log("hello-log")
    assert app.log_path.exists()
    assert "hello-log" in app.log_path.read_text(encoding="utf-8")
    app._on_close()


def test_open_log_opens_log_folder(tmp_path, monkeypatch):
    app = make_app(FakeController(), tmp_path)
    opened = []
    monkeypatch.setattr(
        "socialclub_exporter.gui.os.startfile",
        lambda path: opened.append(path),
    )

    app._open_log()

    assert opened == [str(app.log_path.parent)]
    app._on_close()
