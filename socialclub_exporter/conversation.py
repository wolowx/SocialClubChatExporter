from collections.abc import Sequence

from .completeness import IndexedPage
from .models import Conversation, Message


def _message_sort_key(message: Message) -> tuple[str, int]:
    message_id = int(message.message_id) if message.message_id.isdigit() else 0
    return (message.created_on_utc, message_id)


def build_conversation(
    pages: Sequence[IndexedPage], target_sender_id: str
) -> Conversation:
    selected = [
        page
        for page in pages
        if not page.sender_rockstar_id
        or page.sender_rockstar_id == target_sender_id
    ]
    if not selected:
        raise ValueError("没有该会话的消息页")

    participant_map: dict[str, str] = {}
    for page in selected:
        for participant in page.parsed.participants:
            participant_map.setdefault(participant.rockstar_id, participant.nickname)

    messages_by_id: dict[str, Message] = {}
    for page in selected:
        for message in page.parsed.messages:
            messages_by_id.setdefault(message.message_id, message)

    messages = tuple(sorted(messages_by_id.values(), key=_message_sort_key))
    author_ids = {message.author_id for message in messages}

    self_rockstar_id = next(
        (rockstar_id for rockstar_id in participant_map
         if rockstar_id != target_sender_id),
        None,
    )
    if self_rockstar_id is None:
        self_rockstar_id = next(
            (author_id for author_id in author_ids
             if author_id != target_sender_id),
            "",
        )

    sender_nickname = participant_map.get(target_sender_id, target_sender_id)
    self_nickname = (
        participant_map.get(self_rockstar_id, self_rockstar_id)
        if self_rockstar_id
        else ""
    )
    total = next(
        (page.parsed.total for page in selected
         if page.parsed.total is not None),
        None,
    )

    return Conversation(
        sender_rockstar_id=target_sender_id,
        sender_nickname=sender_nickname,
        self_rockstar_id=self_rockstar_id,
        self_nickname=self_nickname,
        messages=messages,
        total=total,
    )
