from __future__ import annotations

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, Field

from gtd import org, tasks
from gtd.core import Inbox


class InboxConfig(BaseModel):
    config: Annotated[tasks.Config | org.Config, Field(discriminator="kind")]
    destination: bool = False


class AppConfig(BaseModel):
    inbox: list[InboxConfig]


def parse_config(s: str) -> AppConfig:
    return AppConfig.model_validate(yaml.safe_load(s))


def read_config(path: Path | str) -> AppConfig:
    return parse_config(Path(path).read_text())


def build_inbox(config: tasks.Config | org.Config) -> Inbox:
    match config:
        case tasks.Config():
            return tasks.TasksInbox.from_config(config)
        case org.Config():
            return org.OrgInbox.from_config(config)
