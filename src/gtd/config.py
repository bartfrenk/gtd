from __future__ import annotations

import io
from pathlib import Path
from typing import Annotated, cast

import yamlin
from pydantic import BaseModel, Field, model_validator

from gtd import org, spotify, tasks, tickler
from gtd.core import Inbox, log
from gtd.token_cache import TokenCache

_KNOWN_KINDS = {
    cast(str, cls.model_fields["kind"].default)
    for cls in (tasks.Config, org.Config, spotify.Config, tickler.Config)
}


class InboxConfig(BaseModel):
    config: Annotated[
        tasks.Config | org.Config | spotify.Config | tickler.Config, Field(discriminator="kind")
    ]
    destination: bool = False


def _inbox_kind(item: object) -> object | None:
    if not isinstance(item, dict):
        return None
    config = cast(dict[str, object], item).get("config")
    if not isinstance(config, dict):
        return None
    return cast(dict[str, object], config).get("kind")


class AppConfig(BaseModel):
    inbox: list[InboxConfig]

    @model_validator(mode="before")
    @classmethod
    def _drop_unknown_inbox_kinds(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        typed_data = cast(dict[str, object], data)
        inbox = typed_data.get("inbox")
        if not isinstance(inbox, list):
            return typed_data
        kept: list[object] = []
        for item in cast(list[object], inbox):
            kind = _inbox_kind(item)
            if kind is not None and kind not in _KNOWN_KINDS:
                log.warning("Skipping inbox with unknown kind %r", kind)
                continue
            kept.append(item)
        result: dict[str, object] = {**typed_data, "inbox": kept}
        return result


async def parse_config(s: str) -> AppConfig:
    return AppConfig.model_validate(await yamlin.read_stream(io.StringIO(s)))


async def read_config(path: Path | str) -> AppConfig:
    path = Path(path)
    config = AppConfig.model_validate(await yamlin.read_file(path))
    cache = TokenCache.next_to_config(path)
    for inbox_config in config.inbox:
        inbox = inbox_config.config
        if isinstance(inbox, (tasks.Config, spotify.Config)):
            inbox.refresh_token = cache.get(inbox.client_id)
    return config


def build_inbox(config: tasks.Config | org.Config | spotify.Config | tickler.Config) -> Inbox:
    match config:
        case tasks.Config():
            return tasks.TasksInbox.from_config(config)
        case org.Config():
            return org.OrgInbox.from_config(config)
        case spotify.Config():
            return spotify.SpotifyInbox.from_config(config)
        case tickler.Config():
            return tickler.TicklerInbox.from_config(config)
