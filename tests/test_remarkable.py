from pathlib import Path
from typing import final

from remarkable.client import DocumentEntry

from gtd.core import Item, Status
from gtd.hash_cache import HashCache
from gtd.remarkable import RemarkableInbox, _blank_page_pdf, _split_tablet_path


def _entry(hash_: str, visible_name: str = "Inbox", parent: str = "") -> DocumentEntry:
    return DocumentEntry(
        id="doc-1", hash=hash_, visible_name=visible_name, parent=parent, type="DocumentType"
    )


def _folder(id_: str, visible_name: str, parent: str = "") -> DocumentEntry:
    return DocumentEntry(
        id=id_, hash="folder-hash", visible_name=visible_name, parent=parent, type="CollectionType"
    )


@final
class _FakeClient:
    def __init__(self, entries: list[DocumentEntry], pdf_bytes: bytes = b"") -> None:
        self._entries = entries
        self._pdf_bytes = pdf_bytes
        self.downloaded = False
        self.replace_calls: list[tuple[bytes, str | None, str | None]] = []

    async def list_documents(self) -> list[DocumentEntry]:
        return self._entries

    async def download_pdf(self, path: str, dest: Path) -> Path:
        self.downloaded = True
        _ = dest.write_bytes(self._pdf_bytes)
        return dest

    async def replace_pdf(self, path: str, name: str | None = None, folder: str | None = None):
        self.replace_calls.append((Path(path).read_bytes(), name, folder))


@final
class _FakeOCR:
    def __init__(self, items_per_page: list[list[Item]]) -> None:
        self._items_per_page = items_per_page
        self._next_page = 0

    def recognize(self, png: bytes) -> list[Item]:
        items = self._items_per_page[self._next_page]
        self._next_page += 1
        return items


async def test_get_items_skips_download_when_hash_unchanged(tmp_path):
    hash_cache = HashCache(tmp_path / "hash")
    hash_cache.set("abc")
    client = _FakeClient([_entry("abc")])
    inbox = RemarkableInbox("/Inbox", client, hash_cache, _FakeOCR([]))

    items = [item async for item in inbox.get_items()]

    assert items == []
    assert client.downloaded is False


async def test_get_items_downloads_and_ocrs_when_hash_changed(tmp_path):
    hash_cache = HashCache(tmp_path / "hash")
    hash_cache.set("old")
    client = _FakeClient([_entry("new")], pdf_bytes=_blank_page_pdf())
    ocr = _FakeOCR([[Item(title="Buy milk", status=Status.TODO)]])
    inbox = RemarkableInbox("/Inbox", client, hash_cache, ocr)

    items = [item async for item in inbox.get_items()]

    assert client.downloaded is True
    assert [item.title for item in items] == ["Buy milk"]


async def test_get_items_does_not_persist_hash_when_items_are_found(tmp_path):
    """Regression test: run_sync only clear()s a source after add() to the
    destination succeeds. If get_items() persisted the hash itself, a failed
    add() (or a crash before clear() runs) would permanently lose those items
    -- the next sync would see the hash as already "seen" and skip them.
    Persisting only happens in clear(), so a retry re-discovers the same items.
    """
    hash_cache = HashCache(tmp_path / "hash")
    hash_cache.set("old")
    client = _FakeClient([_entry("new")], pdf_bytes=_blank_page_pdf())
    ocr = _FakeOCR([[Item(title="Buy milk", status=Status.TODO)]])
    inbox = RemarkableInbox("/Inbox", client, hash_cache, ocr)

    _ = [item async for item in inbox.get_items()]

    assert hash_cache.get() == "old"


async def test_get_items_persists_hash_immediately_when_no_items_found(tmp_path):
    hash_cache = HashCache(tmp_path / "hash")
    hash_cache.set("old")
    client = _FakeClient([_entry("new")], pdf_bytes=_blank_page_pdf())
    inbox = RemarkableInbox("/Inbox", client, hash_cache, _FakeOCR([[]]))

    items = [item async for item in inbox.get_items()]

    assert items == []
    assert hash_cache.get() == "new"


async def test_get_items_filters_by_status(tmp_path):
    hash_cache = HashCache(tmp_path / "hash")
    client = _FakeClient([_entry("new")], pdf_bytes=_blank_page_pdf())
    ocr = _FakeOCR([[Item(title="A", status=Status.TODO), Item(title="B", status=Status.DONE)]])
    inbox = RemarkableInbox("/Inbox", client, hash_cache, ocr)

    items = [item async for item in inbox.get_items(status={Status.TODO})]

    assert [item.title for item in items] == ["A"]


async def test_get_items_merges_items_across_pages(tmp_path):
    hash_cache = HashCache(tmp_path / "hash")
    client = _FakeClient([_entry("new")], pdf_bytes=_blank_page_pdf())
    ocr = _FakeOCR([[Item(title="A", status=Status.TODO)]])
    inbox = RemarkableInbox("/Inbox", client, hash_cache, ocr)

    items = [item async for item in inbox.get_items()]

    assert [item.title for item in items] == ["A"]


async def test_clear_replaces_with_blank_page_split_from_path(tmp_path):
    hash_cache = HashCache(tmp_path / "hash")
    client = _FakeClient(
        [
            _folder("folder-id", "GTD"),
            _entry("after-clear", visible_name="Inbox", parent="folder-id"),
        ]
    )
    inbox = RemarkableInbox("/GTD/Inbox", client, hash_cache, _FakeOCR([]))

    await inbox.clear()

    [(pdf_bytes, name, folder)] = client.replace_calls
    assert name == "Inbox"
    assert folder == "GTD"
    assert pdf_bytes.startswith(b"%PDF")


async def test_clear_at_root_passes_no_folder(tmp_path):
    hash_cache = HashCache(tmp_path / "hash")
    client = _FakeClient([_entry("after-clear")])
    inbox = RemarkableInbox("/Inbox", client, hash_cache, _FakeOCR([]))

    await inbox.clear()

    [(_, name, folder)] = client.replace_calls
    assert name == "Inbox"
    assert folder is None


async def test_clear_persists_the_post_clear_hash(tmp_path):
    hash_cache = HashCache(tmp_path / "hash")
    hash_cache.set("before-clear")
    client = _FakeClient([_entry("after-clear")])
    inbox = RemarkableInbox("/Inbox", client, hash_cache, _FakeOCR([]))

    await inbox.clear()

    assert hash_cache.get() == "after-clear"


def test_split_tablet_path_root_level():
    assert _split_tablet_path("/Inbox") == ("Inbox", None)


def test_split_tablet_path_nested():
    assert _split_tablet_path("/GTD/Inbox") == ("Inbox", "GTD")
