from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Credentials:
    email: str
    master_token: str


@dataclass
class ChecklistItem:
    text: str
    checked: bool
