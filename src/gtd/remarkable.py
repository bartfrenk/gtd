# pyright: reportAny = false, reportUnknownVariableType = false, reportExplicitAny = false
"""A reMarkable-backed inbox: handwritten to-do items OCR'd via a vision LLM.

See docs/features/remarkable-inbox.md for the design rationale -- in short,
the reMarkable sync protocol is content-addressed with no in-place edit, so
`clear()` recreates the document from a blank template rather than wiping it,
and `get_items()` only pays for the download+OCR pass when the document's
content hash has actually changed since the last successful run.
"""

from __future__ import annotations

import json
import tempfile
from base64 import standard_b64encode
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal, Protocol, Self, final, override

import pymupdf
from anthropic import Anthropic
from anthropic.types import TextBlock
from pydantic import BaseModel
from remarkable.auth import DEFAULT_CREDENTIALS_PATH
from remarkable.client import RemarkableClient, resolve_path

from gtd.core import Inbox, Item, Status
from gtd.hash_cache import HashCache

# Cheap enough that the hash-gating in get_items() is almost beside the point,
# and far better than dedicated OCR engines at reading messy handwriting.
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

_PROMPT = (
    "This image is a page from a handwritten to-do list. List each distinct "
    "handwritten line item as a to-do, in the order it appears on the page. "
    "Ignore items that have a line drawn through them (crossed out). "
    "Respond with only a JSON array of strings, one per item, and no other "
    "commentary or markdown formatting. If there are no legible items, "
    "respond with an empty JSON array: []."
)


class Config(BaseModel):
    kind: Literal["remarkable"] = "remarkable"
    path: str
    hash_cache_path: Path
    credentials_path: Path = DEFAULT_CREDENTIALS_PATH
    anthropic_api_key: str | None = None
    model: str = _DEFAULT_MODEL


class OCREngine(Protocol):
    def recognize(self, png: bytes) -> list[Item]: ...


@final
class ClaudeVisionOCR:
    """Reads handwritten to-do items directly off a rendered page image.

    Prompting a vision LLM to emit the item list directly, rather than
    transcribing raw text and parsing it afterwards, collapses OCR and
    item-splitting into a single step and copes with messy handwriting
    noticeably better than dedicated OCR engines.
    """

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self._model = model
        self._api_key = api_key

    def recognize(self, png: bytes) -> list[Item]:
        client = Anthropic(api_key=self._api_key)
        data = standard_b64encode(png).decode("ascii")
        response = client.messages.create(
            model=self._model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/png", "data": data},
                        },
                        {"type": "text", "text": _PROMPT},
                    ],
                }
            ],
        )
        text = "".join(block.text for block in response.content if isinstance(block, TextBlock))
        titles = _parse_json_string_array(text)
        return [Item(title=title, status=Status.TODO) for title in titles]


@final
class RemarkableInbox(Inbox):
    def __init__(self, path: str, client: Any, hash_cache: HashCache, ocr: OCREngine) -> None:
        self._path = path
        self._client = client
        self._hash_cache = hash_cache
        self._ocr = ocr

    @classmethod
    def from_config(cls, config: Config) -> Self:
        return cls(
            config.path,
            RemarkableClient(credentials_path=config.credentials_path.expanduser()),
            HashCache(config.hash_cache_path),
            ClaudeVisionOCR(config.model, config.anthropic_api_key),
        )

    @override
    async def get_items(self, status: set[Status] | None = None) -> AsyncIterator[Item]:
        entries = await self._client.list_documents()
        entry = resolve_path(entries, self._path)
        if entry.hash == self._hash_cache.get():
            return

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "inbox.pdf"
            _ = await self._client.download_pdf(self._path, dest)
            pdf_bytes = dest.read_bytes()

        items = [item for page in _render_pages(pdf_bytes) for item in self._ocr.recognize(page)]
        self._hash_cache.set(entry.hash)
        for item in items:
            if status is None or item.status in status:
                yield item

    @override
    async def add(self, items: list[Item]) -> None:
        raise NotImplementedError(
            "RemarkableInbox is source-only: mapping an arbitrary GTD item back onto a "
            "handwritten page isn't a well defined operation"
        )

    @override
    async def clear(self) -> None:
        """Recreate the document from a blank page.

        The sync protocol has no in-place edit, so this is "upload a blank
        page, trash the old document" (via `replace_pdf`) rather than wiping
        content -- see the Question 1 discussion in
        docs/features/remarkable-inbox.md.
        """
        name, folder = _split_tablet_path(self._path)
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            _ = tmp.write(_blank_page_pdf())
            tmp.flush()
            _ = await self._client.replace_pdf(tmp.name, name=name, folder=folder)

    @override
    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self._path})"


def _render_pages(pdf_bytes: bytes) -> list[bytes]:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    return [page.get_pixmap().tobytes("png") for page in doc]


def _blank_page_pdf() -> bytes:
    doc = pymupdf.open()
    _ = doc.new_page()
    return doc.tobytes()


def _split_tablet_path(path: str) -> tuple[str, str | None]:
    segments = [s for s in path.strip("/").split("/") if s]
    if not segments:
        raise ValueError(f"Invalid reMarkable document path: {path!r}")
    name = segments[-1]
    folder = "/".join(segments[:-1]) if len(segments) > 1 else None
    return name, folder


def _parse_json_string_array(text: str) -> list[str]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    data = json.loads(text)
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError(f"Expected a JSON array of strings from OCR, got: {text[:200]!r}")
    return data
