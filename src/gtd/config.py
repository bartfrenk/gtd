from __future__ import annotations

import io
from pathlib import Path
from typing import Annotated

import yamlin
from pydantic import BaseModel, Field

from gtd import org, spotify, tasks
from gtd.core import Inbox


class InboxConfig(BaseModel):
    config: Annotated[tasks.Config | org.Config | spotify.Config, Field(discriminator="kind")]
    destination: bool = False


class AppConfig(BaseModel):
    inbox: list[InboxConfig]


async def parse_config(s: str) -> AppConfig:
    return AppConfig.model_validate(await yamlin.read_stream(io.StringIO(s)))


async def read_config(path: Path | str) -> AppConfig:
    return AppConfig.model_validate(await yamlin.read_file(Path(path)))


def build_inbox(config: tasks.Config | org.Config | spotify.Config) -> Inbox:
    match config:
        case tasks.Config():
            return tasks.TasksInbox.from_config(config)
        case org.Config():
            return org.OrgInbox.from_config(config)
        case spotify.Config():
            return spotify.SpotifyInbox.from_config(config)
