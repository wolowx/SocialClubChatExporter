import queue

from mitmproxy import http

from .capture_parser import parse_capture
from .models import CaptureEvent


class MessagingAddon:
    def __init__(self, event_queue: queue.Queue[CaptureEvent]):
        self.event_queue = event_queue

    def response(self, flow: http.HTTPFlow) -> None:
        try:
            event = parse_capture(
                flow.request.pretty_host,
                flow.request.path,
                flow.request.headers,
                flow.request.get_text(strict=False),
                flow.response.get_text(strict=False) if flow.response else "",
            )
        except Exception:
            return
        if event is not None:
            self.event_queue.put(event)
