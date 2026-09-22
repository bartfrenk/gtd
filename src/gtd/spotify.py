# pyright: reportAny = false, reportUnknownVariableType = false, reportExplicitAny = false
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from itertools import batched
from typing import Any, Literal, Self, final, override

from pydantic import BaseModel, Field
from spotipy import Spotify
from spotipy.cache_handler import MemoryCacheHandler
from spotipy.oauth2 import SpotifyOauthError, SpotifyOAuth

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
    playlist_id: str
    client_id: str
    client_secret: str

    # Populated from the token cache after loading, never sourced from config.yaml.
    refresh_token: str | None = Field(default=None, exclude=True)

    @classmethod
    def from_env(cls, playlist_id: str) -> Self:
        return cls(
            playlist_id=playlist_id,
            client_id=os.environ["CLIENT_ID"],
            client_secret=os.environ["CLIENT_SECRET"],
            refresh_token=os.environ["REFRESH_TOKEN"],
        )

    def client(self) -> Any:
        if self.refresh_token is None:
            raise RuntimeError(
                f"No cached refresh token for client_id {self.client_id!r}; "
                "run `gtd auth config` first"
            )
        token_info = self._auth_manager().refresh_access_token(self.refresh_token)
        return Spotify(auth=token_info["access_token"])

    def is_valid(self) -> bool:
        if self.refresh_token is None:
            return False
        try:
            self._auth_manager().refresh_access_token(self.refresh_token)
        except SpotifyOauthError:
            return False
        return True

    def reauthorize(self) -> str:
        return _run_consent_flow(self.client_id, self.client_secret)

    def _auth_manager(self) -> SpotifyOAuth:
        return SpotifyOAuth(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=REDIRECT_URI,
            scope=SPOTIFY_SCOPES,
            cache_handler=MemoryCacheHandler(),
        )


@final
class SpotifyInbox(Inbox):
    def __init__(self, playlist_id: str, client: Any) -> None:
        self._playlist_id = playlist_id
        self._client = client

    @classmethod
    def from_config(cls, config: Config) -> Self:
        return cls(config.playlist_id, config.client())

    @override
    async def get_items(self, status: set[Status] | None = None) -> AsyncIterator[Item]:
        for entry in self._fetch_entries():
            if entry["is_local"] or entry["item"] is None:
                continue
            item = self._to_item(entry["item"])
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
        uris = [
            entry["item"]["uri"]
            for entry in self._fetch_entries()
            if not entry["is_local"] and entry["item"] is not None
        ]
        for batch in batched(uris, _REMOVE_BATCH_SIZE):
            self._client.playlist_remove_all_occurrences_of_items(self._playlist_id, list(batch))

    def _fetch_entries(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        page = self._client.playlist_items(self._playlist_id, additional_types=("track",))
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

    @override
    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self._playlist_id})"


def authorize() -> None:
    client_id = input("Client ID: ")
    client_secret = input("Client secret: ")
    print(_run_consent_flow(client_id, client_secret))


def _run_consent_flow(client_id: str, client_secret: str) -> str:
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
    return token_info["refresh_token"]
