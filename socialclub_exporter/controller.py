import queue
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from .capture_engine import CaptureEngine
from .cert_manager import CertError, CertManager, CertStatus
from .completeness import CompletenessReport, IndexedPage, check_completeness
from .conversation import build_conversation
from .exporter import ExportPaths
from .models import CaptureEvent, Conversation
from .parsing import parse_messages_page
from .proxy_manager import ProxyManager, allocate_free_port
from .settings import AppSettings, app_data_dir, resource_path


class ControllerState(Enum):
    IDLE = "idle"
    WAITING = "waiting"
    CAPTURING = "capturing"
    STOPPING = "stopping"
    VERIFYING = "verifying"
    EXPORTING = "exporting"
    DONE = "done"
    ERROR = "error"


@dataclass(frozen=True)
class ExportResult:
    complete: bool
    report: CompletenessReport
    paths: ExportPaths | None
    message: str


@dataclass
class ControllerCallbacks:
    on_status: Callable[[str], None] = lambda _text: None
    on_progress: Callable[[int, int, int | None, bool | None], None] = (
        lambda _pages, _unique, _total, _has_more: None
    )
    on_log: Callable[[str], None] = lambda _text: None
    on_done: Callable[[ExportResult], None] = lambda _result: None
    on_error: Callable[[str], None] = lambda _text: None


CaptureFactory = Callable[[int, Path, queue.Queue[CaptureEvent]], CaptureEngine]
ExportFn = Callable[[Conversation, Path, Path], ExportPaths]


class ExportController:
    def __init__(
        self,
        settings: AppSettings,
        cert: CertManager,
        proxy: ProxyManager,
        capture_factory: CaptureFactory,
        export_fn: ExportFn,
        callbacks: ControllerCallbacks | None = None,
        port_allocator: Callable[[], int] = allocate_free_port,
    ):
        self.settings = settings
        self.cert = cert
        self.proxy = proxy
        self.capture_factory = capture_factory
        self.export_fn = export_fn
        self.callbacks = callbacks or ControllerCallbacks()
        self.port_allocator = port_allocator

        self.state = ControllerState.IDLE
        self.event_queue: queue.Queue[CaptureEvent] = queue.Queue()
        self.capture: CaptureEngine | None = None
        self.pages: list[IndexedPage] = []
        self.target_sender_id: str | None = None
        self.target_nickname: str | None = None

    def certificate_status(self) -> CertStatus:
        return self.cert.status()

    def install_certificate(self) -> CertStatus:
        status = self.cert.install()
        self._status("证书已安装")
        return status

    def uninstall_certificate(self) -> None:
        self.cert.uninstall()
        self._status("证书已卸载")

    def start_capture(self) -> None:
        if self.state in (
            ControllerState.WAITING,
            ControllerState.CAPTURING,
            ControllerState.STOPPING,
        ):
            raise RuntimeError("capture is already running")

        self.event_queue = queue.Queue()
        self.pages = []
        self.target_sender_id = None
        self.target_nickname = None

        status = self.cert.status()
        if not status.installed:
            self._fail("证书未安装或不受信任，请先安装证书")
            raise CertError("证书未安装或不受信任")

        self.state = ControllerState.WAITING
        self._status("正在准备本地代理...")
        try:
            port = self.port_allocator()
            self.capture = self.capture_factory(
                port,
                app_data_dir() / "mitmproxy",
                self.event_queue,
            )
            self.capture.start()
            self.proxy.set_local(port)
        except Exception as exc:
            self._safe_log(f"启动抓包失败: {exc}")
            self._cleanup()
            self._fail("启动抓包失败，请查看日志")
            raise

        self._status(
            "请按 Home 关闭再打开 Social Club 面板，然后打开对话并往上滚到最早消息；"
            "完成后点“停止并导出”。"
        )

    def poll_capture_events(self) -> list[CaptureEvent]:
        events: list[CaptureEvent] = []
        while True:
            try:
                events.append(self.event_queue.get_nowait())
            except queue.Empty:
                break
        return events

    def on_capture_event(self, event: CaptureEvent) -> None:
        if self.state not in (
            ControllerState.WAITING,
            ControllerState.CAPTURING,
        ):
            return
        try:
            parsed = parse_messages_page(event.response_xml)
        except Exception as exc:
            self._safe_log(f"忽略无法解析的消息页: {exc}")
            return

        sender = event.request.sender_rockstar_id
        if self.target_sender_id is None:
            nickname = next(
                (
                    participant.nickname
                    for participant in parsed.participants
                    if participant.rockstar_id == sender
                ),
                sender,
            )
            wanted = self.settings.target_nickname
            if wanted and nickname.lower() != wanted.lower():
                self._safe_log(
                    f"忽略会话 {nickname}，等待目标 {wanted}"
                )
                self._status(
                    f"已忽略 {nickname} 的会话，等待目标 {wanted}；"
                    "请在 Messages 页签打开目标对话。"
                )
                return
            self.target_sender_id = sender
            self.target_nickname = nickname
            self._status(f"正在捕获与 {nickname} 的会话...")
        elif sender != self.target_sender_id:
            self._safe_log("忽略另一个会话的消息页")
            return

        self.pages.append(
            IndexedPage(
                page_index=event.request.page_index,
                parsed=parsed,
                sender_rockstar_id=sender,
            )
        )
        self.state = ControllerState.CAPTURING

        unique_messages = {
            message.message_id
            for page in self.pages
            for message in page.parsed.messages
        }
        total = next(
            (
                page.parsed.total
                for page in self.pages
                if page.parsed.total is not None
            ),
            None,
        )
        last_has_more = self.pages[-1].parsed.has_more
        self.callbacks.on_progress(
            len(self.pages), len(unique_messages), total, last_has_more
        )
        total_text = f" / 共 {total}" if total is not None else ""
        self._status(
            f"已捕获 {len(self.pages)} 页 / {len(unique_messages)} 条消息"
            f"{total_text}"
        )

    def stop_and_export(self, force: bool = False) -> ExportResult:
        report = check_completeness(self.pages)

        if not self.pages:
            self._cleanup()
            self.state = ControllerState.IDLE
            message = "没有捕获到任何消息"
            self._status(message)
            result = ExportResult(False, report, None, message)
            self.callbacks.on_done(result)
            return result

        self.state = ControllerState.STOPPING
        self._status("正在停止并校验...")
        self._cleanup()

        if not report.complete and not force:
            self.state = ControllerState.IDLE
            message = (
                "捕获不完整："
                + "；".join(report.reasons)
                + "。请继续往上滚加载，或选择只导出已捕获部分。"
            )
            self._status(message)
            self._safe_log(message)
            result = ExportResult(False, report, None, message)
            self.callbacks.on_done(result)
            return result

        if self.target_sender_id is None:
            message = "没有识别到目标会话"
            self._fail(message)
            return ExportResult(False, report, None, message)

        try:
            conversation = build_conversation(
                self.pages, self.target_sender_id
            )
            self.state = ControllerState.EXPORTING
            self._status("正在导出...")
            paths = self.export_fn(
                conversation,
                self.settings.output_root,
                resource_path("resources/chat_template.html"),
            )
            self.state = ControllerState.DONE
            message = (
                "导出完成"
                if report.complete
                else "导出完成（数据不完整，已按你的要求导出）"
            )
            self._status(message)
            result = ExportResult(report.complete, report, paths, message)
            self.callbacks.on_done(result)
            return result
        except Exception as exc:
            self._safe_log(f"导出失败: {exc}")
            self._fail("导出失败，请查看日志")
            return ExportResult(False, report, None, "导出失败")

    def close(self) -> None:
        self._cleanup()
        self.state = ControllerState.IDLE
        self._status("已停止")

    def abort_capture(self, message: str) -> None:
        self._cleanup()
        self.state = ControllerState.IDLE
        self._status(message)
        self._safe_log(message)
        self.callbacks.on_error(message)

    def _cleanup(self) -> None:
        capture = self.capture
        self.capture = None
        if capture is not None:
            try:
                capture.stop()
            except Exception as exc:
                self._safe_log(f"停止抓包失败: {exc}")
        try:
            self.proxy.restore()
        except Exception as exc:
            self._safe_log(f"恢复代理失败: {exc}")

    def _fail(self, message: str) -> None:
        self.state = ControllerState.ERROR
        self._status(message)
        self._safe_log(message)
        self.callbacks.on_error(message)

    def _status(self, message: str) -> None:
        self.callbacks.on_status(message)

    def _safe_log(self, message: str) -> None:
        cleaned = re.sub(
            r'SCAUTH val="[^"]*"',
            'SCAUTH val="***"',
            str(message),
        )
        cleaned = re.sub(
            r'(?i)(ScAuthToken|SessionTicket|SessionKey|RememberedMachineToken)'
            r'\s*[:=]\s*"?[^",\s]+',
            r"\1=***",
            cleaned,
        )
        self.callbacks.on_log(cleaned)
