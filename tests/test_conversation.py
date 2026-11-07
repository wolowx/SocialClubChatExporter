import pytest

from socialclub_exporter.completeness import IndexedPage
from socialclub_exporter.conversation import build_conversation
from socialclub_exporter.models import Message, ParsedPage, Participant

PARTICIPANTS = (
    Participant("111111111", "SelfUser"),
    Participant("222222222", "TargetUser"),
)


def msg(message_id, author_id, created_on, text="x"):
    return Message(str(message_id), str(author_id), f"nick-{author_id}", created_on, text)


def page(page_index, sender_id, messages, participants=PARTICIPANTS, total=999):
    return IndexedPage(
        page_index=page_index,
        parsed=ParsedPage(
            participants=tuple(participants),
            messages=tuple(messages),
            total=total,
            has_more=False,
            next_page_index=None,
        ),
        sender_rockstar_id=sender_id,
    )


def test_duplicate_messages_are_deduped():
    pages = [
        page(0, "222222222", [msg(3, 222222222, "2026-01-01T00:00:03Z")]),
        page(1, "222222222", [msg(3, 222222222, "2026-01-01T00:00:03Z"), msg(2, 111111111, "2026-01-01T00:00:02Z")]),
    ]
    conversation = build_conversation(pages, "222222222")
    assert [m.message_id for m in conversation.messages] == ["2", "3"]


def test_messages_are_sorted_by_created_on():
    pages = [
        page(0, "222222222", [msg(3, 222222222, "2026-01-01T00:00:03Z")]),
        page(1, "222222222", [msg(1, 111111111, "2026-01-01T00:00:01Z")]),
        page(2, "222222222", [msg(2, 222222222, "2026-01-01T00:00:02Z")]),
    ]
    conversation = build_conversation(pages, "222222222")
    assert [m.message_id for m in conversation.messages] == ["1", "2", "3"]


def test_participants_and_target_are_identified():
    conversation = build_conversation(
        [page(0, "222222222", [msg(1, 222222222, "2026-01-01T00:00:01Z")])],
        "222222222",
    )
    assert conversation.sender_rockstar_id == "222222222"
    assert conversation.sender_nickname == "TargetUser"
    assert conversation.self_rockstar_id == "111111111"
    assert conversation.self_nickname == "SelfUser"
    assert conversation.total == 999


def test_pages_from_other_senders_are_ignored():
    pages = [
        page(0, "222222222", [msg(1, 222222222, "2026-01-01T00:00:01Z")]),
        page(0, "999", [msg(99, 999, "2026-01-01T00:00:99Z")]),
    ]
    conversation = build_conversation(pages, "222222222")
    assert [m.message_id for m in conversation.messages] == ["1"]


def test_missing_participants_fall_back_to_message_authors():
    pages = [
        page(
            0,
            "222222222",
            [
                msg(1, 222222222, "2026-01-01T00:00:01Z"),
                msg(2, 111111111, "2026-01-01T00:00:02Z"),
            ],
            participants=(),
        )
    ]
    conversation = build_conversation(pages, "222222222")
    assert conversation.self_rockstar_id == "111111111"
    assert conversation.self_nickname == "111111111"
    assert conversation.sender_nickname == "222222222"


def test_empty_pages_raise():
    with pytest.raises(ValueError):
        build_conversation([], "222222222")
