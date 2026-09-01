from __future__ import annotations

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, Field

from gtd import tasks

InboxConfig = Annotated[tasks.Config, Field(discriminator="kind")]


class AppConfig(BaseModel):
    inbox: list[InboxConfig]


def parse_config(s: str) -> AppConfig:
    return AppConfig.model_validate(yaml.safe_load(s))


def read_config(path: Path | str) -> AppConfig:
    return parse_config(Path(path).read_text())
