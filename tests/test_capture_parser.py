import queue

from socialclub_exporter.addon import MessagingAddon
from socialclub_exporter.capture_parser import is_messaging_request, parse_capture

SAMPLE_XML = """<MessagesViewModel><Status>true</Status>
<ParticipantList><Participants>
<Participant><RockstarId>111111111</RockstarId><ScNickname>SelfUser</ScNickname></Participant>
<Participant><RockstarId>222222222</RockstarId><ScNickname>TargetUser</ScNickname></Participant>
</Participants></ParticipantList>
<Messages Total="1"><Messages>
<Message><ID>1</ID><AuthorId>222222222</AuthorId><Text>hello</Text><CreatedOn>2026-09-13T08:49:48.36Z</CreatedOn><ScNickname>TargetUser</ScNickname></Message>
</Messages></Messages><HasMore>false</HasMore><NextPageIndex>1</NextPageIndex></MessagesViewModel>"""

HEADERS = {"Authorization": 'SCAUTH val="secret-token"'}
BODY = (
    '{"env":"prod","title":"gta5","version":11,'
    '"senderRockstarId":"222222222","pageIndex":0}'
)


def test_is_messaging_request_filters_host_and_path():
    assert is_messaging_request(
        "scui.rockstargames.com", "/api/messaging/getmessages"
    )
    assert not is_messaging_request(
        "example.com", "/api/messaging/getmessages"
    )
    assert not is_messaging_request(
        "scui.rockstargames.com", "/api/friend/getfriends"
    )


def test_parse_capture_returns_event_for_messaging_request():
    event = parse_capture(
        "scui.rockstargames.com",
        "/api/messaging/getmessages",
        HEADERS,
        BODY,
        SAMPLE_XML,
    )
    assert event is not None
    assert event.request.sender_rockstar_id == "222222222"
    assert event.response_xml == SAMPLE_XML


def test_parse_capture_ignores_missing_auth():
    assert parse_capture(
        "scui.rockstargames.com",
        "/api/messaging/getmessages",
        {},
        BODY,
        SAMPLE_XML,
    ) is None


class FakeRequest:
    pretty_host = "scui.rockstargames.com"
    path = "/api/messaging/getmessages"
    headers = HEADERS

    def get_text(self, strict=False):
        return BODY


class FakeResponse:
    def get_text(self, strict=False):
        return SAMPLE_XML


class FakeFlow:
    request = FakeRequest()
    response = FakeResponse()


class NonMessagingFlow:
    request = type(
        "Request",
        (),
        {
            "pretty_host": "example.com",
            "path": "/api/messaging/getmessages",
            "headers": HEADERS,
            "get_text": lambda self, strict=False: BODY,
        },
    )()
    response = FakeResponse()


def test_addon_puts_capture_event_in_queue():
    events = queue.Queue()
    MessagingAddon(events).response(FakeFlow())
    event = events.get_nowait()
    assert event.request.sender_rockstar_id == "222222222"


def test_addon_ignores_non_messaging_flow():
    events = queue.Queue()
    MessagingAddon(events).response(NonMessagingFlow())
    assert events.empty()
