from socialclub_exporter.parsing import (
    extract_scauth_token,
    parse_capture,
    parse_capture_request,
    parse_messages_page,
)

SAMPLE_XML = """<MessagesViewModel xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <Status>true</Status>
  <ParticipantList><Participants>
    <Participant><RockstarId>111111111</RockstarId><ScNickname>SelfUser</ScNickname></Participant>
    <Participant><RockstarId>222222222</RockstarId><ScNickname>TargetUser</ScNickname></Participant>
  </Participants></ParticipantList>
  <Messages Total="999"><Messages>
    <Message><ID>2</ID><AuthorId>222222222</AuthorId><Text>hello</Text><CreatedOn>2026-09-13T08:49:48.36Z</CreatedOn><ScNickname>TargetUser</ScNickname></Message>
    <Message><ID>1</ID><AuthorId>111111111</AuthorId><Text>hi</Text><CreatedOn>2026-09-13T08:49:00Z</CreatedOn><ScNickname>SelfUser</ScNickname></Message>
  </Messages></Messages>
  <HasMore>true</HasMore><NextPageIndex>1</NextPageIndex>
</MessagesViewModel>"""

HEADERS = {"Authorization": 'SCAUTH val="secret-token"'}
BODY = (
    '{"env":"prod","title":"gta5","version":11,'
    '"senderRockstarId":"222222222","pageIndex":0}'
)


def test_parse_messages_page_reads_participants_messages_and_paging():
    page = parse_messages_page(SAMPLE_XML)
    assert [p.rockstar_id for p in page.participants] == ["111111111", "222222222"]
    assert [p.nickname for p in page.participants] == ["SelfUser", "TargetUser"]
    assert [m.text for m in page.messages] == ["hello", "hi"]
    assert [m.author_id for m in page.messages] == ["222222222", "111111111"]
    assert page.total == 999
    assert page.has_more is True
    assert page.next_page_index == 1


def test_extract_scauth_token_is_case_insensitive():
    assert extract_scauth_token({"authorization": 'SCAUTH val="abc"'}) == "abc"
    assert extract_scauth_token({"Authorization": "Bearer abc"}) is None
    assert extract_scauth_token({}) is None


def test_parse_capture_request_reads_request_fields():
    req = parse_capture_request(HEADERS, BODY)
    assert req is not None
    assert req.token == "secret-token"
    assert req.sender_rockstar_id == "222222222"
    assert req.env == "prod"
    assert req.title == "gta5"
    assert req.version == 11
    assert req.page_index == 0


def test_parse_capture_request_returns_none_for_missing_auth_or_bad_body():
    assert parse_capture_request({}, BODY) is None
    assert parse_capture_request(HEADERS, "not-json") is None
    assert parse_capture_request(HEADERS, '{"env":"prod"}') is None


def test_parse_capture_filters_host_and_path():
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

    assert parse_capture(
        "example.com", "/api/messaging/getmessages", HEADERS, BODY, SAMPLE_XML
    ) is None
    assert parse_capture(
        "scui.rockstargames.com", "/api/friend/getfriends", HEADERS, BODY, SAMPLE_XML
    ) is None


def test_parse_messages_page_missing_has_more_is_none():
    xml = SAMPLE_XML.replace("<HasMore>true</HasMore>", "")
    page = parse_messages_page(xml)
    assert page.has_more is None
