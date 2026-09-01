from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum


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


class Inbox(ABC):

    @abstractmethod
    def get_items(self, status: set[Status] | None = None) -> AsyncIterator[Item]: ...
