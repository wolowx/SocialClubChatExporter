from dataclasses import dataclass


@dataclass(frozen=True)
class Participant:
    rockstar_id: str
    nickname: str
    avatar_url: str = ""


@dataclass(frozen=True)
class Message:
    message_id: str
    author_id: str
    author_nickname: str
    created_on_utc: str
    text: str


@dataclass(frozen=True)
class Conversation:
    sender_rockstar_id: str
    sender_nickname: str
    self_rockstar_id: str
    self_nickname: str
    messages: tuple[Message, ...]
    total: int | None


@dataclass(frozen=True)
class ParsedPage:
    participants: tuple[Participant, ...]
    messages: tuple[Message, ...]
    total: int | None
    has_more: bool | None
    next_page_index: int | None


@dataclass(frozen=True)
class CaptureRequest:
    token: str
    sender_rockstar_id: str
    env: str
    title: str
    version: int
    page_index: int


@dataclass(frozen=True)
class CaptureEvent:
    request: CaptureRequest
    response_xml: str
