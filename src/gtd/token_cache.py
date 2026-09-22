from __future__ import annotations

from pathlib import Path
from typing import Self, final


@final
class TokenCache:
    """A directory holding one refresh token per file, named by client_id."""

    def __init__(self, directory: Path) -> None:
        self._directory: Path = directory

    @classmethod
    def next_to_config(cls, config_path: Path | str) -> Self:
        return cls(Path(config_path).parent / "tokens")

    def get(self, client_id: str) -> str | None:
        path = self._directory / client_id
        return path.read_text().strip() if path.exists() else None

    def set(self, client_id: str, refresh_token: str) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / client_id
        path.write_text(refresh_token)
        path.chmod(0o600)
