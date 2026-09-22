import pytest

from gtd import tasks
from gtd.config import AppConfig, InboxConfig, parse_config, read_config


@pytest.mark.integration
async def test_read_config():
    config = await read_config("config.yaml")
    assert isinstance(config, AppConfig)
    assert config.inbox
    for inbox in config.inbox:
        assert isinstance(inbox, InboxConfig)
        assert isinstance(inbox.destination, bool)


async def test_destination_defaults_to_false():
    config = await parse_config(
        """
        inbox:
          - config:
              kind: org
              path: ~/inbox.org
        """
    )
    assert config.inbox[0].destination is False
    assert config.inbox[0].config.kind == "org"


async def test_read_config_populates_refresh_token_from_cache(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
        inbox:
          - config:
              kind: tasks
              title: Inbox
              client_id: cid
              client_secret: csec
        """
    )
    tokens_dir = tmp_path / "tokens"
    tokens_dir.mkdir()
    (tokens_dir / "cid").write_text("cached-token")

    config = await read_config(config_path)

    inbox_config = config.inbox[0].config
    assert isinstance(inbox_config, tasks.Config)
    assert inbox_config.refresh_token == "cached-token"


async def test_read_config_leaves_refresh_token_none_when_uncached(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
        inbox:
          - config:
              kind: tasks
              title: Inbox
              client_id: cid
              client_secret: csec
        """
    )

    config = await read_config(config_path)

    inbox_config = config.inbox[0].config
    assert isinstance(inbox_config, tasks.Config)
    assert inbox_config.refresh_token is None
