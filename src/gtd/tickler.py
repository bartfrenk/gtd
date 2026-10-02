# pyright: reportPrivateUsage = false, reportUnnecessaryComparison = false
# orgparse types OrgDate.start as always-present (DateIsh) even though it's None
# whenever there's no SCHEDULED/DEADLINE/CLOSED line, and node.scheduled._repeater /
# ._warning have no public accessor at all.
from __future__ import annotations

import calendar
from collections.abc import AsyncIterator
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Literal, Self, final, override

import orgparse
from orgparse.date import OrgDateScheduled
from orgparse.node import OrgNode
from pydantic import BaseModel

from gtd.core import Inbox, Item, Status, strip_blank_lines


class Config(BaseModel):
    kind: Literal["tickler"] = "tickler"
    path: Path


@final
class TicklerInbox(Inbox):
    """An org-backed inbox whose items only surface once their SCHEDULED date arrives.

    `clear()` therefore doesn't truncate the file like `OrgInbox.clear()` does: it
    removes exactly the items `get_items()` would currently return (rescheduling
    repeating ones to their next occurrence instead of dropping them), leaving
    not-yet-due items untouched.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path).expanduser()

    @classmethod
    def from_config(cls, config: Config) -> Self:
        return cls(config.path)

    @override
    async def get_items(self, status: set[Status] | None = None) -> AsyncIterator[Item]:
        for node in orgparse.load(self._path)[1:]:
            if node.todo is None:
                continue
            item = self._to_item(node)
            if not _is_due(item):
                continue
            if status is None or item.status in status:
                yield item

    @staticmethod
    def _to_item(node: OrgNode) -> Item:
        todo = node.todo or "TODO"
        scheduled = node.scheduled.start
        return Item(
            title=node.heading,
            description=strip_blank_lines(node.body) or None,
            status=Status.__members__.get(todo, Status.TODO),
            available_at=_as_datetime(scheduled) if scheduled is not None else None,
        )

    @override
    async def add(self, items: list[Item]) -> None:
        text = self._path.read_text() if self._path.exists() else ""
        if text and not text.endswith("\n"):
            text += "\n"
        text += "\n".join(self._to_org(item) for item in items) + "\n"
        self._path.write_text(text)

    @staticmethod
    def _to_org(item: Item) -> str:
        status = item.status or Status.TODO
        lines = [f"* {status.value} {item.title}"]
        if item.available_at is not None:
            lines.append(f"SCHEDULED: {_format_date(item.available_at.date())}")
        if item.description:
            lines.append(item.description)
        return "\n".join(lines)

    @override
    async def clear(self) -> None:
        root = orgparse.load(self._path)
        today = date.today()
        blocks = [root.body] if root.body else []
        for node in root[1:]:
            scheduled = node.scheduled if node.scheduled.start is not None else None
            if node.todo is None or not _scheduled_is_due(scheduled, today):
                blocks.append(_render_node(node, scheduled))
                continue
            if scheduled is None or scheduled._repeater is None:
                continue
            repeater = scheduled._repeater
            next_date = _next_occurrence(repeater, _as_date(scheduled.start), today)
            next_scheduled = OrgDateScheduled(
                next_date, repeater=repeater, warning=scheduled._warning
            )
            blocks.append(_render_node(node, next_scheduled))
        text = "\n".join(blocks)
        if text and not text.endswith("\n"):
            text += "\n"
        self._path.write_text(text)

    @override
    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self._path})"


def _is_due(item: Item) -> bool:
    return item.available_at is None or item.available_at.date() <= date.today()


def _scheduled_is_due(scheduled: OrgDateScheduled | None, today: date) -> bool:
    return scheduled is None or _as_date(scheduled.start) <= today


def _as_datetime(d: date) -> datetime:
    return d if isinstance(d, datetime) else datetime.combine(d, time.min)


def _as_date(d: date) -> date:
    return d.date() if isinstance(d, datetime) else d


def _format_date(d: date) -> str:
    return f"<{d.strftime('%Y-%m-%d %a')}>"


def _render_node(node: OrgNode, scheduled: OrgDateScheduled | None) -> str:
    todo = f"{node.todo} " if node.todo else ""
    heading = f"{'*' * (node.level or 1)} {todo}{node.heading}"
    tags = node.shallow_tags
    if tags:
        heading += "  :" + ":".join(sorted(tags)) + ":"
    lines = [heading]
    if scheduled is not None:
        lines.append(f"SCHEDULED: {scheduled}")
    body = strip_blank_lines(node.body)
    if body:
        lines.append(body)
    return "\n".join(lines)


def _next_occurrence(repeater: tuple[str, int, str], original: date, today: date) -> date:
    prefix, n, unit = repeater
    if prefix == ".+":
        return _advance(today, n, unit)
    next_date = original
    while next_date <= today:
        next_date = _advance(next_date, n, unit)
    return next_date


def _advance(d: date, n: int, unit: str) -> date:
    if unit == "d":
        return d + timedelta(days=n)
    if unit == "w":
        return d + timedelta(weeks=n)
    if unit == "m":
        month_index = d.month - 1 + n
        year = d.year + month_index // 12
        month = month_index % 12 + 1
        day = min(d.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    if unit == "y":
        try:
            return d.replace(year=d.year + n)
        except ValueError:
            return d.replace(year=d.year + n, day=28)
    raise ValueError(f"Unsupported repeater unit: {unit!r}")
