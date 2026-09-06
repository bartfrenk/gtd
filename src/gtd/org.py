from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal, Self, final, override

import orgparse
from orgparse.node import OrgNode
from pydantic import BaseModel

from gtd.core import Inbox, Item, Status


class Config(BaseModel):
    kind: Literal["org"] = "org"
    path: Path


@final
class OrgInbox(Inbox):
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
            if status is None or item.status in status:
                yield item

    @staticmethod
    def _to_item(node: OrgNode) -> Item:
        todo = node.todo or "TODO"
        return Item(
            title=node.heading,
            description=node.body.strip() or None,
            status=Status.__members__.get(todo, Status.TODO),
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
        heading = f"* {status.value} {item.title}"
        return f"{heading}\n{item.description}" if item.description else heading

    @override
    async def clear(self) -> None:
        self._path.write_text("")

    @override
    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self._path})"
