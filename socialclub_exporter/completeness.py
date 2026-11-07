from dataclasses import dataclass
from collections.abc import Sequence

from .models import ParsedPage


@dataclass(frozen=True)
class IndexedPage:
    page_index: int
    parsed: ParsedPage
    sender_rockstar_id: str = ""


@dataclass(frozen=True)
class CompletenessReport:
    total: int | None
    unique_messages: int
    pages_present: tuple[int, ...]
    missing_pages: tuple[int, ...]
    last_page_index: int | None
    last_page_has_more: bool | None
    complete: bool
    reasons: tuple[str, ...]


def check_completeness(pages: Sequence[IndexedPage]) -> CompletenessReport:
    if not pages:
        return CompletenessReport(
            total=None,
            unique_messages=0,
            pages_present=(),
            missing_pages=(),
            last_page_index=None,
            last_page_has_more=None,
            complete=False,
            reasons=("没有捕获到任何消息页",),
        )

    unique_ids = {
        message.message_id
        for page in pages
        for message in page.parsed.messages
    }
    total = next(
        (page.parsed.total for page in pages if page.parsed.total is not None),
        None,
    )
    pages_present = tuple(sorted({page.page_index for page in pages}))
    last_page_index = pages_present[-1]
    last_page = next(page for page in pages if page.page_index == last_page_index)
    last_page_has_more = last_page.parsed.has_more
    missing_pages = tuple(
        index for index in range(last_page_index + 1)
        if index not in pages_present
    )

    reasons: list[str] = []
    if any(len(page.parsed.messages) == 0 for page in pages):
        reasons.append("存在空消息页")
    if not unique_ids:
        reasons.append("没有捕获到任何消息")
    if total is not None and len(unique_ids) != total:
        reasons.append(
            f"消息数不一致：已捕获 {len(unique_ids)}，服务端总数 {total}"
        )
    if missing_pages:
        reasons.append(f"缺少页：{list(missing_pages)}")
    if last_page_has_more is True:
        reasons.append("最后一页仍有更多消息，可能还没加载到最早")
    elif last_page_has_more is None:
        reasons.append("无法判断是否已到最早消息")

    return CompletenessReport(
        total=total,
        unique_messages=len(unique_ids),
        pages_present=pages_present,
        missing_pages=missing_pages,
        last_page_index=last_page_index,
        last_page_has_more=last_page_has_more,
        complete=not reasons,
        reasons=tuple(reasons),
    )
