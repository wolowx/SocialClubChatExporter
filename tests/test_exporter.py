import csv
import json
import re
from datetime import datetime

from socialclub_exporter.exporter import (
    build_export_records,
    export_conversation,
    render_html,
    sanitize_filename,
)
from socialclub_exporter.models import Conversation, Message

TEMPLATE_PATH = "socialclub_exporter/resources/chat_template.html"


def make_conversation():
    return Conversation(
        sender_rockstar_id="222222222",
        sender_nickname="TargetUser",
        self_rockstar_id="111111111",
        self_nickname="SelfUser",
        messages=(
            Message("1", "111111111", "SelfUser", "2026-01-01T00:00:00Z", "hi"),
            Message("2", "222222222", "TargetUser", "2026-01-01T00:00:01Z", "hello"),
        ),
        total=2,
    )


def test_sanitize_filename_removes_invalid_characters():
    cleaned = sanitize_filename('TargetUser/..:*?<>|"\\')
    assert cleaned
    assert not any(char in cleaned for char in '<>:"/\\|?*')


def test_build_export_records_marks_self_and_local_time():
    records = build_export_records(make_conversation())
    assert [record["author_display"] for record in records] == ["我", "TargetUser"]
    assert records[0]["created_on_local"].startswith("2026-01-01T08:00:00")
    assert records[0]["created_on_local"].endswith("+08:00")
    assert records[1]["text"] == "hello"


def test_render_html_replaces_placeholders_and_embeds_data():
    records = build_export_records(make_conversation())
    template = open(TEMPLATE_PATH, encoding="utf-8").read()
    html = render_html(records, "TargetUser", "SelfUser", template)

    assert "TargetUser" in html
    assert "SelfUser" in html
    assert "__CHAT_DATA__" not in html
    assert "__TARGET_NAME_JSON__" not in html
    assert "hello" in html
    assert "SCAUTH" not in html

    match = re.search(
        r'<script id="chat-data" type="application/json">(.*?)</script>',
        html,
        re.S,
    )
    assert match is not None
    assert len(json.loads(match.group(1))) == 2


def test_render_html_uses_conversation_self_id():
    records = build_export_records(make_conversation())
    template = open(TEMPLATE_PATH, encoding="utf-8").read()
    html = render_html(
        records, "TargetUser", "SelfUser", template, self_id="999"
    )
    assert 'var SELF_ID = "999";' in html


def test_render_html_escapes_script_breakout_in_nickname():
    template = open(TEMPLATE_PATH, encoding="utf-8").read()
    html = render_html(
        [],
        "x</script><script>alert(1)</script>",
        "me",
        template,
        self_id="1",
    )
    assert "</script><script>alert(1)</script>" not in html
    assert "<\\/script>" in html


def test_export_conversation_writes_html_txt_csv_json(tmp_path):
    paths = export_conversation(
        make_conversation(),
        tmp_path,
        TEMPLATE_PATH,
        now=datetime(2026, 11, 7, 12, 0, 0),
    )

    assert paths.directory.name == "TargetUser_20261107_120000"
    assert paths.html.exists()
    assert paths.txt.exists()
    assert paths.csv.exists()
    assert paths.json.exists()

    txt = paths.txt.read_text(encoding="utf-8")
    assert "[2026-01-01 08:00:00] 我: hi" in txt

    with paths.csv.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0].keys()) == [
        "created_on_utc",
        "created_on_local",
        "author",
        "author_id",
        "author_nickname",
        "message_id",
        "text",
    ]
    assert rows[0]["author"] == "我"
    assert rows[1]["author"] == "TargetUser"

    data = json.loads(paths.json.read_text(encoding="utf-8"))
    assert len(data) == 2

    for path in (paths.html, paths.txt, paths.csv, paths.json):
        content = path.read_text(encoding="utf-8")
        assert "SCAUTH" not in content
        assert "secret-token" not in content
