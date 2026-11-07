import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping

from .models import (
    CaptureEvent,
    CaptureRequest,
    Message,
    ParsedPage,
    Participant,
)

_SCAUTH_RE = re.compile(r'SCAUTH val="([^"]+)"')
_MESSAGING_HOSTS = {"scui.rockstargames.com", "scapi.rockstargames.com"}
_MESSAGING_PATH = "/api/messaging/getmessages"


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return str(value)
    return None


def extract_scauth_token(headers: Mapping[str, str]) -> str | None:
    value = _header_value(headers, "Authorization")
    if not value:
        return None
    match = _SCAUTH_RE.search(value)
    return match.group(1) if match else None


def parse_messages_page(xml: str) -> ParsedPage:
    root = ET.fromstring(xml)

    participants = tuple(
        Participant(
            rockstar_id=(node.findtext("RockstarId") or "").strip(),
            nickname=(node.findtext("ScNickname") or "").strip(),
            avatar_url=(node.findtext("AvatarUrl") or "").strip(),
        )
        for node in root.findall(".//Participant")
    )

    total_node = root.find(".//Messages")
    total: int | None = None
    if total_node is not None and total_node.get("Total"):
        try:
            total = int(total_node.get("Total"))
        except ValueError:
            total = None

    messages = tuple(
        Message(
            message_id=(node.findtext("ID") or "").strip(),
            author_id=(node.findtext("AuthorId") or "").strip(),
            author_nickname=(node.findtext("ScNickname") or "").strip(),
            created_on_utc=(node.findtext("CreatedOn") or "").strip(),
            text=node.findtext("Text") or "",
        )
        for node in root.findall(".//Message")
    )

    has_more_text = root.findtext(".//HasMore")
    has_more: bool | None
    if has_more_text is None:
        has_more = None
    else:
        has_more = has_more_text.strip().lower() == "true"

    next_text = (root.findtext(".//NextPageIndex") or "").strip()
    next_page_index: int | None = None
    if next_text:
        try:
            next_page_index = int(next_text)
        except ValueError:
            next_page_index = None

    return ParsedPage(
        participants=participants,
        messages=messages,
        total=total,
        has_more=has_more,
        next_page_index=next_page_index,
    )


def parse_capture_request(
    headers: Mapping[str, str], body: str
) -> CaptureRequest | None:
    token = extract_scauth_token(headers)
    if not token:
        return None
    try:
        data = json.loads(body)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    sender = data.get("senderRockstarId")
    if sender is None or str(sender).strip() == "":
        return None
    try:
        page_index = int(data.get("pageIndex", 0))
        version = int(data.get("version", 0))
    except (TypeError, ValueError):
        return None
    return CaptureRequest(
        token=token,
        sender_rockstar_id=str(sender),
        env=str(data.get("env", "")),
        title=str(data.get("title", "")),
        version=version,
        page_index=page_index,
    )


def is_messaging_request(host: str, path: str) -> bool:
    return host in _MESSAGING_HOSTS and path.startswith(_MESSAGING_PATH)


def parse_capture(
    host: str,
    path: str,
    headers: Mapping[str, str],
    body: str,
    response_body: str,
) -> CaptureEvent | None:
    if not is_messaging_request(host, path):
        return None
    request = parse_capture_request(headers, body)
    if request is None:
        return None
    return CaptureEvent(request=request, response_xml=response_body)
