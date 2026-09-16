from __future__ import annotations

from gtd import org
from gtd.core import Item, Status


async def test_add_records_source_when_present(tmp_path):
    path = tmp_path / "inbox.org"
    inbox = org.OrgInbox(path)

    await inbox.add([Item(title="a", status=Status.TODO, source="tasks")])

    assert path.read_text() == "* TODO a\nSource: tasks\n"


async def test_add_records_source_and_description_when_both_present(tmp_path):
    path = tmp_path / "inbox.org"
    inbox = org.OrgInbox(path)

    await inbox.add(
        [Item(title="a", status=Status.TODO, source="spotify", description="https://example.com")]
    )

    assert path.read_text() == "* TODO a\nSource: spotify\n\nhttps://example.com\n"


async def test_add_omits_source_line_when_absent(tmp_path):
    path = tmp_path / "inbox.org"
    inbox = org.OrgInbox(path)

    await inbox.add([Item(title="a", status=Status.TODO)])

    assert path.read_text() == "* TODO a\n"
