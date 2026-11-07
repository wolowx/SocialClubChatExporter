from pathlib import Path

import pytest

from socialclub_exporter.cert_manager import CertError, CertStatus
from socialclub_exporter.controller import (
    ControllerCallbacks,
    ControllerState,
    ExportController,
)
from socialclub_exporter.exporter import ExportPaths
from socialclub_exporter.models import CaptureEvent, CaptureRequest
from socialclub_exporter.proxy_manager import ProxySettings
from socialclub_exporter.settings import AppSettings

PARTICIPANTS = (("111111111", "SelfUser"), ("222222222", "TargetUser"))


def make_event(
    page_index=0,
    total=2,
    has_more=False,
    messages=None,
    participants=PARTICIPANTS,
    sender="222222222",
):
    if messages is None:
        messages = [
            (1, 111111111, "hi", "2026-01-01T00:00:00Z"),
            (2, 222222222, "hello", "2026-01-01T00:00:01Z"),
        ]
    parts = "".join(
        f"<Participant><RockstarId>{rid}</RockstarId>"
        f"<ScNickname>{nick}</ScNickname></Participant>"
        for rid, nick in participants
    )
    msgs = "".join(
        f"<Message><ID>{mid}</ID><AuthorId>{author}</AuthorId>"
        f"<Text>{text}</Text><CreatedOn>{ts}</CreatedOn>"
        f"<ScNickname>{author}</ScNickname></Message>"
        for mid, author, text, ts in messages
    )
    xml = (
        "<MessagesViewModel><ParticipantList><Participants>"
        f"{parts}</Participants></ParticipantList>"
        f'<Messages Total="{total}"><Messages>{msgs}</Messages></Messages>'
        f"<HasMore>{str(has_more).lower()}</HasMore>"
        f"<NextPageIndex>{page_index + 1}</NextPageIndex></MessagesViewModel>"
    )
    return CaptureEvent(
        CaptureRequest("secret-token", sender, "prod", "gta5", 11, page_index),
        xml,
    )


class Recorder:
    def __init__(self):
        self.statuses = []
        self.progresses = []
        self.logs = []
        self.results = []
        self.errors = []

    def status(self, text):
        self.statuses.append(text)

    def progress(self, pages, unique, total, has_more):
        self.progresses.append((pages, unique, total, has_more))

    def log(self, text):
        self.logs.append(text)

    def done(self, result):
        self.results.append(result)

    def error(self, text):
        self.errors.append(text)


class FakeCert:
    def __init__(self, installed=True):
        self.installed = installed
        self.install_calls = 0
        self.uninstall_calls = 0

    def status(self):
        return CertStatus(Path("cert.cer"), "thumb", self.installed)

    def install(self):
        self.installed = True
        self.install_calls += 1
        return self.status()

    def uninstall(self):
        self.installed = False
        self.uninstall_calls += 1


class FakeProxy:
    def __init__(self, events=None):
        self.set_calls = []
        self.restore_calls = 0
        self.events = events if events is not None else []

    def set_local(self, port):
        self.set_calls.append(port)
        self.events.append("proxy_set")
        return ProxySettings(0, "", "", None)

    def restore(self):
        self.restore_calls += 1
        return True

    def restore_if_stale(self, port):
        return False


class FakeCapture:
    def __init__(self, port, confdir, event_queue, events=None):
        self.port = port
        self.confdir = confdir
        self.event_queue = event_queue
        self.events = events if events is not None else []
        self.started = False
        self.stopped = False
        self.raise_on_start = False
        self.raise_on_stop = False

    def start(self):
        if self.raise_on_start:
            raise RuntimeError('SCAUTH val="secret-token"')
        self.started = True
        self.events.append("capture_start")

    def stop(self):
        if self.raise_on_stop:
            raise RuntimeError("stop boom")
        self.stopped = True

    @property
    def running(self):
        return self.started and not self.stopped


class FakeExport:
    def __init__(self, paths):
        self.paths = paths
        self.calls = []

    def __call__(self, conversation, output_root, template_path):
        self.calls.append((conversation, output_root, template_path))
        return self.paths


def make_controller(
    tmp_path,
    installed=True,
    target=None,
    raise_on_start=False,
    port_allocator=None,
):
    settings = AppSettings(
        output_root=tmp_path / "out",
        target_nickname=target,
        proxy_port=18888,
    )
    cert = FakeCert(installed)
    events = []
    proxy = FakeProxy(events)
    record = Recorder()
    created = {"events": events}

    def factory(port, confdir, event_queue):
        capture = FakeCapture(port, confdir, event_queue, events)
        capture.raise_on_start = raise_on_start
        created["capture"] = capture
        return capture

    paths = ExportPaths(
        directory=tmp_path / "out",
        html=tmp_path / "out" / "a.html",
        txt=tmp_path / "out" / "a.txt",
        csv=tmp_path / "out" / "a.csv",
        json=tmp_path / "out" / "a.json",
    )
    export = FakeExport(paths)
    callbacks = ControllerCallbacks(
        on_status=record.status,
        on_progress=record.progress,
        on_log=record.log,
        on_done=record.done,
        on_error=record.error,
    )
    controller = ExportController(
        settings,
        cert,
        proxy,
        factory,
        export,
        callbacks,
        port_allocator=port_allocator or (lambda: 19001),
    )
    return controller, cert, proxy, record, created, export, paths


def test_start_capture_requires_trusted_certificate(tmp_path):
    controller, cert, proxy, record, created, _, _ = make_controller(
        tmp_path, installed=False
    )
    with pytest.raises(CertError):
        controller.start_capture()

    assert proxy.set_calls == []
    assert "capture" not in created
    assert controller.state == ControllerState.ERROR
    assert record.errors


def test_start_capture_sets_proxy_and_starts_engine(tmp_path):
    controller, _, proxy, record, created, _, _ = make_controller(tmp_path)
    controller.start_capture()

    assert proxy.set_calls == [19001]
    assert created["capture"].started is True
    assert controller.state == ControllerState.WAITING
    assert record.statuses


def test_proxy_is_set_after_capture_starts(tmp_path):
    controller, _, _, _, created, _, _ = make_controller(tmp_path)
    controller.start_capture()

    assert created["events"] == ["capture_start", "proxy_set"]


def test_second_start_uses_fresh_port(tmp_path):
    ports = iter([19001, 19002])
    controller, _, proxy, _, _, _, _ = make_controller(
        tmp_path, port_allocator=lambda: next(ports)
    )
    controller.start_capture()
    controller.on_capture_event(make_event(total=2, has_more=False))
    controller.stop_and_export()

    controller.start_capture()

    assert proxy.set_calls == [19001, 19002]


def test_poll_capture_events_drains_queue(tmp_path):
    controller, _, _, _, _, _, _ = make_controller(tmp_path)
    first = make_event()
    second = make_event()
    controller.event_queue.put(first)
    controller.event_queue.put(second)

    assert controller.poll_capture_events() == [first, second]
    assert controller.poll_capture_events() == []


def test_on_capture_event_accumulates_and_reports_progress(tmp_path):
    controller, _, _, record, _, _, _ = make_controller(tmp_path)
    controller.start_capture()
    controller.on_capture_event(make_event(total=2, has_more=False))

    assert controller.target_nickname == "TargetUser"
    assert record.progresses[-1] == (1, 2, 2, False)
    assert controller.state == ControllerState.CAPTURING


def test_non_target_conversation_is_ignored_until_target_arrives(tmp_path):
    controller, _, proxy, record, created, _, _ = make_controller(
        tmp_path, target="TargetUser"
    )
    controller.start_capture()
    controller.on_capture_event(
        make_event(
            participants=(("111111111", "SelfUser"), ("222222222", "Other"))
        )
    )

    assert controller.pages == []
    assert controller.target_sender_id is None
    assert controller.state == ControllerState.WAITING
    assert created["capture"].stopped is False
    assert proxy.restore_calls == 0
    assert any(
        "忽略" in log or "等待" in log for log in record.logs
    )

    controller.on_capture_event(
        make_event(
            participants=(
                ("111111111", "SelfUser"),
                ("222222222", "TargetUser"),
            )
        )
    )

    assert len(controller.pages) == 1
    assert controller.target_sender_id == "222222222"
    assert controller.target_nickname == "TargetUser"
    assert controller.state == ControllerState.CAPTURING


def test_stop_and_export_complete(tmp_path):
    controller, _, proxy, _, created, export, paths = make_controller(tmp_path)
    controller.start_capture()
    controller.on_capture_event(
        make_event(
            0,
            total=4,
            has_more=True,
            messages=[
                (1, 111111111, "a", "2026-01-01T00:00:00Z"),
                (2, 222222222, "b", "2026-01-01T00:00:01Z"),
            ],
        )
    )
    controller.on_capture_event(
        make_event(
            1,
            total=4,
            has_more=False,
            messages=[
                (3, 111111111, "c", "2026-01-01T00:00:02Z"),
                (4, 222222222, "d", "2026-01-01T00:00:03Z"),
            ],
        )
    )

    result = controller.stop_and_export()

    assert result.complete is True
    assert result.paths is paths
    assert export.calls
    assert created["capture"].stopped is True
    assert proxy.restore_calls == 1
    assert controller.state == ControllerState.DONE


def test_stop_and_export_incomplete_does_not_export(tmp_path):
    controller, _, proxy, _, created, export, _ = make_controller(tmp_path)
    controller.start_capture()
    controller.on_capture_event(make_event(0, total=999, has_more=True))

    result = controller.stop_and_export()

    assert result.complete is False
    assert result.paths is None
    assert export.calls == []
    assert created["capture"].stopped is True
    assert proxy.restore_calls == 1
    assert result.report.reasons


def test_force_exports_incomplete_with_warning(tmp_path):
    controller, _, _, _, _, export, paths = make_controller(tmp_path)
    controller.start_capture()
    controller.on_capture_event(make_event(0, total=999, has_more=True))

    result = controller.stop_and_export(force=True)

    assert result.paths is paths
    assert export.calls
    assert "不完整" in result.message


def test_close_restores_proxy(tmp_path):
    controller, _, proxy, _, _, _, _ = make_controller(tmp_path)
    controller.close()
    assert proxy.restore_calls == 1


def test_logs_redact_scauth(tmp_path):
    controller, _, _, record, _, _, _ = make_controller(tmp_path)
    controller._safe_log('SCAUTH val="secret"')
    assert all("secret" not in line for line in record.logs)
    assert any("***" in line for line in record.logs)


def test_install_and_uninstall_certificate(tmp_path):
    controller, cert, _, _, _, _, _ = make_controller(tmp_path, installed=False)
    controller.install_certificate()
    assert cert.install_calls == 1
    controller.uninstall_certificate()
    assert cert.uninstall_calls == 1


def test_stale_event_after_close_is_ignored(tmp_path):
    controller, _, _, _, _, _, _ = make_controller(tmp_path)
    controller.start_capture()
    controller.close()
    controller.event_queue.put(make_event())
    for event in controller.poll_capture_events():
        controller.on_capture_event(event)

    assert controller.pages == []
    assert controller.state == ControllerState.IDLE


def test_start_capture_recreates_event_queue(tmp_path):
    controller, _, _, _, _, _, _ = make_controller(tmp_path)
    old_queue = controller.event_queue
    old_queue.put(make_event())
    controller.start_capture()

    assert controller.event_queue is not old_queue
    assert controller.poll_capture_events() == []


def test_abort_capture_restores_proxy_and_stops(tmp_path):
    controller, _, proxy, record, created, _, _ = make_controller(tmp_path)
    controller.start_capture()
    controller.abort_capture("timeout")

    assert controller.state == ControllerState.IDLE
    assert created["capture"].stopped is True
    assert proxy.restore_calls == 1
    assert record.errors


def test_stop_and_export_restores_proxy_when_capture_stop_raises(tmp_path):
    controller, _, proxy, _, created, export, _ = make_controller(tmp_path)
    controller.start_capture()
    controller.on_capture_event(make_event(0, total=2, has_more=False))
    created["capture"].raise_on_stop = True

    result = controller.stop_and_export()

    assert proxy.restore_calls == 1
    assert export.calls
    assert result.paths is not None


def test_force_with_no_pages_does_not_export(tmp_path):
    controller, _, _, _, _, export, _ = make_controller(tmp_path)
    result = controller.stop_and_export(force=True)

    assert result.paths is None
    assert export.calls == []


def test_start_failure_does_not_log_token(tmp_path):
    controller, _, proxy, record, _, _, _ = make_controller(
        tmp_path, raise_on_start=True
    )
    with pytest.raises(RuntimeError):
        controller.start_capture()

    assert proxy.restore_calls == 1
    assert all("secret-token" not in line for line in record.logs)
