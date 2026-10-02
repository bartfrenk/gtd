from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import orgparse

from gtd.core import Item, Status
from gtd.tickler import TicklerInbox

HEADER = "#+TODO: TODO NEXT WAITING URGENT | DONE CANCELLED\n\n"

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
FUTURE = TODAY + timedelta(days=30)


def _ts(d: date, repeater: str = "") -> str:
    suffix = f" {repeater}" if repeater else ""
    return f"<{d.strftime('%Y-%m-%d %a')}{suffix}>"


def _write(path: Path, body: str) -> None:
    path.write_text(HEADER + body)


async def test_get_items_includes_items_with_no_scheduled_date(tmp_path):
    path = tmp_path / "tickler.org"
    _write(path, "* TODO Someday maybe\n")

    items = [item async for item in TicklerInbox(path).get_items()]

    assert [item.title for item in items] == ["Someday maybe"]
    assert items[0].available_at is None


async def test_get_items_excludes_items_not_yet_due(tmp_path):
    path = tmp_path / "tickler.org"
    _write(path, f"* WAITING Follow up later\n  SCHEDULED: {_ts(FUTURE)}\n")

    items = [item async for item in TicklerInbox(path).get_items()]

    assert items == []


async def test_get_items_includes_items_due_today_or_earlier(tmp_path):
    path = tmp_path / "tickler.org"
    _write(
        path,
        f"* TODO Due today\n  SCHEDULED: {_ts(TODAY)}\n"
        f"* TODO Overdue\n  SCHEDULED: {_ts(YESTERDAY)}\n",
    )

    items = [item async for item in TicklerInbox(path).get_items()]

    assert {item.title for item in items} == {"Due today", "Overdue"}


async def test_get_items_applies_status_filter(tmp_path):
    path = tmp_path / "tickler.org"
    _write(
        path,
        f"* TODO A todo\n  SCHEDULED: {_ts(TODAY)}\n"
        f"* WAITING A waiting item\n  SCHEDULED: {_ts(TODAY)}\n",
    )

    items = [item async for item in TicklerInbox(path).get_items(status={Status.WAITING})]

    assert [item.title for item in items] == ["A waiting item"]


async def test_add_round_trips_item_with_no_schedule(tmp_path):
    path = tmp_path / "tickler.org"
    inbox = TicklerInbox(path)

    await inbox.add(
        [Item(title="Renew passport", description="in case they forget", status=Status.TODO)]
    )

    items = [item async for item in inbox.get_items()]
    assert len(items) == 1
    assert items[0].title == "Renew passport"
    assert items[0].description == "in case they forget"
    assert items[0].status == Status.TODO
    assert items[0].available_at is None


async def test_add_round_trips_due_scheduled_item(tmp_path):
    path = tmp_path / "tickler.org"
    inbox = TicklerInbox(path)
    past_dt = datetime.combine(YESTERDAY, datetime.min.time())

    await inbox.add([Item(title="Overdue item", status=Status.TODO, available_at=past_dt)])

    items = [item async for item in inbox.get_items()]
    assert len(items) == 1
    assert items[0].title == "Overdue item"
    assert items[0].available_at is not None
    assert items[0].available_at.date() == YESTERDAY


async def test_add_round_trips_future_scheduled_item(tmp_path):
    path = tmp_path / "tickler.org"
    inbox = TicklerInbox(path)
    future_dt = datetime.combine(FUTURE, datetime.min.time())

    await inbox.add([Item(title="Future item", status=Status.TODO, available_at=future_dt)])

    assert [item async for item in inbox.get_items()] == []

    text = path.read_text()
    assert "SCHEDULED" in text
    assert FUTURE.strftime("%Y-%m-%d") in text


async def test_clear_drops_due_item_without_repeater(tmp_path):
    path = tmp_path / "tickler.org"
    _write(path, f"* WAITING Due no repeat\n  SCHEDULED: {_ts(YESTERDAY)}\n")

    await TicklerInbox(path).clear()

    assert [item async for item in TicklerInbox(path).get_items()] == []
    assert "Due no repeat" not in path.read_text()


async def test_clear_keeps_not_yet_due_items_untouched(tmp_path):
    path = tmp_path / "tickler.org"
    _write(path, f"* NEXT Not due yet\n  SCHEDULED: {_ts(FUTURE)}\n")

    await TicklerInbox(path).clear()

    # Still not due, so get_items() continues to hide it...
    assert [item async for item in TicklerInbox(path).get_items()] == []

    # ...but it's still in the file, unchanged, for when it does become due.
    node = next(iter(orgparse.load(path)[1:]))
    assert node.heading == "Not due yet"
    assert node.todo == "NEXT"
    assert node.scheduled.start == FUTURE


async def test_clear_drops_items_with_no_scheduled_date(tmp_path):
    # A tickler item with no SCHEDULED date is "due" immediately (same as get_items()
    # treats it), so once promoted it has nothing left to wait for.
    path = tmp_path / "tickler.org"
    _write(path, "* TODO No date item\n")

    await TicklerInbox(path).clear()

    items = [item async for item in TicklerInbox(path).get_items()]
    assert items == []
    assert "No date item" not in path.read_text()


async def test_clear_reschedules_due_item_with_cumulative_repeater(tmp_path):
    path = tmp_path / "tickler.org"
    original = TODAY - timedelta(days=100)
    _write(path, f"* TODO Weekly check-in\n  SCHEDULED: {_ts(original, '+1w')}\n")

    await TicklerInbox(path).clear()

    assert [item async for item in TicklerInbox(path).get_items()] == []

    root_text = path.read_text()
    assert "Weekly check-in" in root_text
    assert "+1w" in root_text

    node = next(iter(orgparse.load(path)[1:]))
    assert node.scheduled.start > TODAY
    # anchored to the original weekday, stepped forward in whole weeks
    assert (node.scheduled.start - original).days % 7 == 0


async def test_clear_reschedules_due_item_with_from_today_repeater(tmp_path):
    path = tmp_path / "tickler.org"
    original = TODAY - timedelta(days=100)
    _write(path, f"* TODO Re-read later\n  SCHEDULED: {_ts(original, '.+3d')}\n")

    await TicklerInbox(path).clear()

    node = next(iter(orgparse.load(path)[1:]))
    assert node.scheduled.start == TODAY + timedelta(days=3)
    assert node.scheduled._repeater == (".+", 3, "d")


def test_str_includes_path():
    inbox = TicklerInbox("/tmp/tickler.org")
    assert str(inbox) == "TicklerInbox(/tmp/tickler.org)"


async def test_get_items_keeps_indentation_of_first_body_line(tmp_path):
    path = tmp_path / "tickler.org"
    _write(path, f"* TODO Check reply\n  SCHEDULED: {_ts(TODAY)}\n [2026-10-02 Fri 19:22]\n")

    items = [item async for item in TicklerInbox(path).get_items()]

    assert items[0].description == " [2026-10-02 Fri 19:22]"


async def test_clear_keeps_indentation_of_first_body_line(tmp_path):
    path = tmp_path / "tickler.org"
    _write(path, f"* NEXT Not due yet\n  SCHEDULED: {_ts(FUTURE)}\n [2026-10-02 Fri 19:22]\n")

    await TicklerInbox(path).clear()

    assert path.read_text().endswith("\n [2026-10-02 Fri 19:22]\n")

