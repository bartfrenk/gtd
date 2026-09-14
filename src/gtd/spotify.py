# pyright: reportAny = false, reportUnknownVariableType = false, reportExplicitAny = false
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from itertools import batched
from typing import Any, Literal, Self, final, override

from pydantic import BaseModel
from spotipy import Spotify
from spotipy.cache_handler import MemoryCacheHandler
from spotipy.oauth2 import SpotifyOAuth

from gtd.core import Inbox, Item, Status

SPOTIFY_SCOPES = [
    "playlist-read-private",
    "playlist-modify-private",
    "playlist-modify-public",
]

# Must exactly match a redirect URI registered in the Spotify Developer Dashboard app.
REDIRECT_URI = "http://127.0.0.1:8080/callback"

# Spotify's Web API caps items per request on the playlist items-removal endpoint.
_REMOVE_BATCH_SIZE = 100


class Config(BaseModel):
    kind: Literal["spotify"] = "spotify"
    playlist: str
    client_id: str
    client_secret: str
    refresh_token: str

    @classmethod
    def from_env(cls, playlist: str) -> Self:
        return cls(
            playlist=playlist,
            client_id=os.environ["CLIENT_ID"],
            client_secret=os.environ["CLIENT_SECRET"],
            refresh_token=os.environ["REFRESH_TOKEN"],
        )

    def client(self) -> Any:
        auth_manager = SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=REDIRECT_URI,
            scope=SPOTIFY_SCOPES,
            cache_handler=MemoryCacheHandler(),
        )
        token_info = auth_manager.refresh_access_token(self.refresh_token)
        return Spotify(auth=token_info["access_token"])


@final
class SpotifyInbox(Inbox):
    def __init__(self, playlist: str, client: Any) -> None:
        self._playlist = playlist
        self._client = client

    @classmethod
    def from_config(cls, config: Config) -> Self:
        return cls(config.playlist, config.client())

    @override
    async def get_items(self, status: set[Status] | None = None) -> AsyncIterator[Item]:
        for entry in self._fetch_entries():
            if entry["is_local"] or entry["track"] is None:
                continue
            item = self._to_item(entry["track"])
            if status is None or item.status in status:
                yield item

    @override
    async def add(self, items: list[Item]) -> None:
        raise NotImplementedError(
            "SpotifyInbox is source-only: mapping an arbitrary GTD item back onto a "
            "Spotify track isn't a well defined operation"
        )

    @override
    async def clear(self) -> None:
        playlist_id = self._find_playlist_id()
        uris = [
            entry["track"]["uri"]
            for entry in self._list_entries(playlist_id)
            if not entry["is_local"] and entry["track"] is not None
        ]
        for batch in batched(uris, _REMOVE_BATCH_SIZE):
            self._client.playlist_remove_all_occurrences_of_items(playlist_id, list(batch))

    def _fetch_entries(self) -> list[dict[str, Any]]:
        return self._list_entries(self._find_playlist_id())

    def _list_entries(self, playlist_id: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        page = self._client.playlist_items(playlist_id, additional_types=("track",))
        while page is not None:
            entries.extend(page["items"])
            page = self._client.next(page)
        return entries

    @staticmethod
    def _to_item(track: dict[str, Any]) -> Item:
        artists = ", ".join(artist["name"] for artist in track["artists"])
        return Item(
            title=f"{track['name']} — {artists}",
            description=track["external_urls"]["spotify"],
            status=Status.TODO,
        )

    def _find_playlist_id(self) -> str:
        matches = [p for p in self._fetch_playlists() if p["name"] == self._playlist]
        if len(matches) == 0:
            raise LookupError(f"No playlist found with name {self._playlist!r}")
        if len(matches) > 1:
            raise LookupError(f"Multiple playlists found with name {self._playlist!r}")
        return matches[0]["id"]

    def _fetch_playlists(self) -> list[dict[str, Any]]:
        playlists: list[dict[str, Any]] = []
        page = self._client.current_user_playlists()
        while page is not None:
            playlists.extend(page["items"])
            page = self._client.next(page)
        return playlists

    @override
    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self._playlist})"


def authorize() -> None:
    client_id = input("Client ID: ")
    client_secret = input("Client secret: ")
    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=REDIRECT_URI,
        scope=SPOTIFY_SCOPES,
        cache_handler=MemoryCacheHandler(),
    )
    print(f"Go to the following URL and authorize access:\n{auth_manager.get_authorize_url()}")
    response = input("Enter the URL you were redirected to: ")
    code = auth_manager.parse_response_code(response)
    token_info = auth_manager.get_access_token(code, as_dict=True)
    print(token_info["refresh_token"])  # pyright: ignore[reportUnknownArgumentType]
