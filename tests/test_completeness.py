from socialclub_exporter.completeness import IndexedPage, check_completeness
from socialclub_exporter.models import Message, ParsedPage


def make_page(page_index, ids, total=12, has_more=True):
    messages = tuple(
        Message(str(i), "1", "self", "2026-01-01T00:00:00Z", "x") for i in ids
    )
    return IndexedPage(
        page_index=page_index,
        parsed=ParsedPage(
            participants=(),
            messages=messages,
            total=total,
            has_more=has_more,
            next_page_index=page_index + 1,
        ),
    )


def test_complete_when_total_matches_and_last_page_has_no_more():
    pages = [
        make_page(0, [1, 2, 3, 4]),
        make_page(1, [5, 6, 7, 8]),
        make_page(2, [9, 10, 11, 12], has_more=False),
    ]
    report = check_completeness(pages)
    assert report.complete is True
    assert report.reasons == ()
    assert report.unique_messages == 12
    assert report.pages_present == (0, 1, 2)
    assert report.last_page_has_more is False


def test_missing_page_is_incomplete():
    pages = [
        make_page(0, [1, 2, 3, 4]),
        make_page(2, [9, 10, 11, 12], has_more=False),
    ]
    report = check_completeness(pages)
    assert report.complete is False
    assert report.missing_pages == (1,)
    assert any("缺少页" in reason for reason in report.reasons)


def test_total_mismatch_is_incomplete():
    report = check_completeness([make_page(0, [1], total=999, has_more=False)])
    assert report.complete is False
    assert any("消息数不一致" in reason for reason in report.reasons)


def test_last_page_with_more_is_incomplete():
    report = check_completeness([make_page(0, [1], total=1, has_more=True)])
    assert report.complete is False
    assert any("仍有更多" in reason for reason in report.reasons)


def test_empty_capture_is_incomplete():
    report = check_completeness([])
    assert report.complete is False
    assert report.reasons


def test_empty_page_is_incomplete():
    report = check_completeness(
        [
            IndexedPage(
                0,
                ParsedPage(
                    participants=(),
                    messages=(),
                    total=None,
                    has_more=False,
                    next_page_index=None,
                ),
            )
        ]
    )
    assert report.complete is False
    assert report.reasons
