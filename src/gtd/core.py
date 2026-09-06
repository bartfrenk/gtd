import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum

log = logging.getLogger("gtd")


def init_logging(debug: bool) -> None:
    logging.basicConfig(level=logging.WARNING)
    log.setLevel(logging.DEBUG if debug else logging.WARNING)


class Status(StrEnum):
    TODO = "TODO"
    URGENT = "URGENT"
    NEXT = "NEXT"
    WAITING = "WAITING"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


@dataclass
class Item:
    title: str
    description: str | None = None
    status: Status | None = None


OPEN_STATUSES = frozenset({Status.TODO, Status.URGENT, Status.NEXT, Status.WAITING})


class Inbox(ABC):

    @abstractmethod
    def get_items(self, status: set[Status] | None = None) -> AsyncIterator[Item]: ...

    @abstractmethod
    async def add(self, items: list[Item]) -> None: ...

    @abstractmethod
    async def clear(self) -> None: ...
