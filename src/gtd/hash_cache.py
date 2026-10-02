from __future__ import annotations

from pathlib import Path
from typing import final


@final
class HashCache:
    """A single file holding the last-seen content hash of one remote document."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path).expanduser()

    def get(self) -> str | None:
        return self._path.read_text().strip() if self._path.exists() else None

    def set(self, hash_: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        _ = self._path.write_text(hash_)
