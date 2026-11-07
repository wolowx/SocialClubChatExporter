import csv
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Conversation

LOCAL_TZ = timezone(timedelta(hours=8))
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_CSV_FIELDS = [
    "created_on_utc",
    "created_on_local",
    "author",
    "author_id",
    "author_nickname",
    "message_id",
    "text",
]


@dataclass(frozen=True)
class ExportPaths:
    directory: Path
    html: Path
    txt: Path
    csv: Path
    json: Path


def sanitize_filename(name: str) -> str:
    cleaned = _INVALID_FILENAME_CHARS.sub("_", name).strip().strip(".")
    return cleaned or "conversation"


def _parse_utc(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _created_on_local(value: str) -> str:
    parsed = _parse_utc(value)
    if parsed is None:
        return ""
    return parsed.astimezone(LOCAL_TZ).isoformat()


def build_export_records(conversation: Conversation) -> list[dict]:
    records: list[dict] = []
    for message in conversation.messages:
        if message.author_id == conversation.self_rockstar_id:
            author_display = "我"
        elif message.author_id == conversation.sender_rockstar_id:
            author_display = conversation.sender_nickname
        else:
            author_display = message.author_nickname or message.author_id
        records.append(
            {
                "message_id": message.message_id,
                "author_id": message.author_id,
                "author_nickname": message.author_nickname,
                "author_display": author_display,
                "created_on_utc": message.created_on_utc,
                "created_on_local": _created_on_local(message.created_on_utc),
                "text": message.text,
            }
        )
    return records


def _json_for_script(value: str) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def render_html(
    records: list[dict],
    target_name: str,
    self_name: str,
    template_text: str,
    self_id: str = "",
) -> str:
    payload = json.dumps(
        records, ensure_ascii=False, separators=(",", ":")
    ).replace("</", "<\\/")

    result = template_text
    result = result.replace("__TARGET_NAME_HTML__", html.escape(target_name))
    result = result.replace("__SELF_NAME_HTML__", html.escape(self_name))
    result = result.replace(
        "__TARGET_NAME_JSON__", _json_for_script(target_name)
    )
    result = result.replace("__SELF_NAME_JSON__", _json_for_script(self_name))
    result = result.replace("__SELF_ID_JSON__", _json_for_script(self_id))
    result = result.replace("__CHAT_DATA__", payload)
    return result


def _write_txt(path: Path, conversation: Conversation, records: list[dict]) -> None:
    lines = [
        f"与 {conversation.sender_nickname} 的 Social Club 私信记录",
        f"消息总数: {len(records)}",
        "=" * 60,
        "",
    ]
    for record in records:
        parsed = _parse_utc(record["created_on_utc"])
        stamp = (
            parsed.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
            if parsed
            else record["created_on_utc"]
        )
        text = (record["text"] or "").replace("\r\n", "\n").replace("\r", "\n")
        parts = text.split("\n")
        lines.append(
            f"[{stamp}] {record['author_display']}: {parts[0]}"
        )
        for extra in parts[1:]:
            lines.append(f"    {extra}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "created_on_utc": record["created_on_utc"],
                    "created_on_local": record["created_on_local"],
                    "author": record["author_display"],
                    "author_id": record["author_id"],
                    "author_nickname": record["author_nickname"],
                    "message_id": record["message_id"],
                    "text": record["text"],
                }
            )


def export_conversation(
    conversation: Conversation,
    output_root: Path,
    template_path: Path,
    now: datetime | None = None,
) -> ExportPaths:
    now = now or datetime.now()
    safe_name = sanitize_filename(conversation.sender_nickname)
    directory = Path(output_root) / f"{safe_name}_{now.strftime('%Y%m%d_%H%M%S')}"
    directory.mkdir(parents=True, exist_ok=True)

    records = build_export_records(conversation)
    template_text = Path(template_path).read_text(encoding="utf-8")
    html_text = render_html(
        records,
        conversation.sender_nickname,
        conversation.self_nickname,
        template_text,
        conversation.self_rockstar_id,
    )

    paths = ExportPaths(
        directory=directory,
        html=directory / f"{safe_name}_chat.html",
        txt=directory / f"{safe_name}_chat.txt",
        csv=directory / f"{safe_name}_chat.csv",
        json=directory / f"{safe_name}_chat.json",
    )
    paths.html.write_text(html_text, encoding="utf-8")
    _write_txt(paths.txt, conversation, records)
    _write_csv(paths.csv, records)
    paths.json.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return paths
