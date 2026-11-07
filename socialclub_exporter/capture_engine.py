import asyncio
import queue
import socket
import threading
import time
from pathlib import Path

from mitmproxy import options
from mitmproxy.tools.dump import DumpMaster

from .addon import MessagingAddon
from .models import CaptureEvent


class CaptureEngine:
    def __init__(
        self,
        port: int,
        confdir: Path,
        event_queue: queue.Queue[CaptureEvent],
    ):
        self.port = port
        self.confdir = Path(confdir)
        self.event_queue = event_queue
        self._thread: threading.Thread | None = None
        self._master: DumpMaster | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._started = threading.Event()
        self._error: BaseException | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self.confdir.mkdir(parents=True, exist_ok=True)
        self._started.clear()
        self._error = None
        self._thread = threading.Thread(
            target=self._run,
            name="mitmproxy-capture",
            daemon=True,
        )
        self._thread.start()
        if not self._started.wait(timeout=15):
            raise RuntimeError("mitmproxy did not start in time")
        if self._error is not None:
            raise RuntimeError(
                f"mitmproxy failed to start: {self._error}"
            ) from self._error
        if not self._wait_until_listening(timeout=10):
            error = self._error
            self.stop()
            raise RuntimeError(f"mitmproxy failed to start: {error}")

    def _wait_until_listening(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._error is not None:
                return False
            if self._thread is None or not self._thread.is_alive():
                return False
            try:
                with socket.create_connection(
                    ("127.0.0.1", self.port), timeout=0.25
                ):
                    pass
            except OSError:
                time.sleep(0.1)
                continue
            time.sleep(0.2)
            if (
                self._error is not None
                or self._thread is None
                or not self._thread.is_alive()
            ):
                return False
            return True
        return False

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        loop.set_exception_handler(lambda _loop, _context: None)
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            opts = options.Options(
                listen_host="127.0.0.1",
                listen_port=self.port,
                confdir=str(self.confdir),
            )
            master = DumpMaster(
                opts,
                loop=loop,
                with_termlog=False,
                with_dumper=False,
            )
            master.addons.add(MessagingAddon(self.event_queue))
            self._master = master
            self._started.set()
            loop.run_until_complete(master.run())
        except BaseException as exc:
            self._error = exc
            self._started.set()
        finally:
            try:
                loop.close()
            except Exception:
                pass

    def stop(self) -> None:
        master = self._master
        if master is not None:
            loop = getattr(master, "event_loop", None)
            if loop is not None and not loop.is_closed():
                try:
                    master.shutdown()
                except RuntimeError:
                    pass
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._thread = None
        self._master = None
        self._loop = None
