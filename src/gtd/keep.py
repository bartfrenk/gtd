from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import gkeepapi
import gkeepapi.node


@dataclass
class Credentials:
    email: str
    master_token: str


@dataclass
class ChecklistItem:
    text: str
    checked: bool


class KeepNoteClient:
    def __init__(
        self,
        title: str,
        credentials: Credentials,
        keep_factory: Callable[[], gkeepapi.Keep] = gkeepapi.Keep,
    ) -> None:
        self._title = title
        self._credentials = credentials
        self._keep_factory = keep_factory
        self._keep: gkeepapi.Keep | None = None

    def fetch_items(self) -> list[ChecklistItem]:
        keep = self._authenticated_keep()
        note = self._find_note(keep)
        return [ChecklistItem(text=item.text, checked=item.checked) for item in note.items]

    def _authenticated_keep(self) -> gkeepapi.Keep:
        if self._keep is None:
            keep = self._keep_factory()
            keep.authenticate(self._credentials.email, self._credentials.master_token)
            self._keep = keep
        return self._keep

    def _find_note(self, keep: gkeepapi.Keep) -> gkeepapi.node.List:
        matches = list(keep.find(func=lambda node: node.title == self._title))
        if len(matches) == 0:
            raise LookupError(f"No note found with title {self._title!r}")
        if len(matches) > 1:
            raise LookupError(f"Multiple notes found with title {self._title!r}")
        note = matches[0]
        if not isinstance(note, gkeepapi.node.List):
            raise TypeError(f"Note {self._title!r} is not a checklist note")
        return note
