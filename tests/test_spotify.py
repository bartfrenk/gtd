import os
from typing import Any, final

import pytest

from gtd.core import Item
from gtd.spotify import Config, SpotifyInbox


@pytest.mark.integration
async def test_get_items_reads_real_playlist():
    config = Config.from_env(os.environ["PLAYLIST_ID"])
    inbox = SpotifyInbox.from_config(config)

    items = [item async for item in inbox.get_items()]
    for item in items:
        print(item)
    assert all(isinstance(item, Item) for item in items)


def _entry(name: str, artist_names: list[str | None]) -> dict[str, Any]:
    track = {
        "name": name,
        "artists": [{"name": artist_name} for artist_name in artist_names],
        "external_urls": {"spotify": "https://open.spotify.com/track/1"},
    }
    return {"is_local": False, "item": track}


@final
class _FakeClient:
    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self._entries = entries

    def playlist_items(self, playlist_id: str, additional_types: tuple[str, ...]) -> Any:
        return {"items": self._entries}

    def next(self, page: Any) -> Any:
        return None


async def test_get_items_includes_artist_names():
    inbox = SpotifyInbox("playlist-id", _FakeClient([_entry("Song", ["Artist A", "Artist B"])]))
    items = [item async for item in inbox.get_items()]
    assert items[0].title == "Song — Artist A, Artist B"


async def test_get_items_falls_back_to_track_name_when_an_artist_name_is_none():
    inbox = SpotifyInbox("playlist-id", _FakeClient([_entry("Song", ["Artist A", None])]))
    items = [item async for item in inbox.get_items()]
    assert items[0].title == "Song"
