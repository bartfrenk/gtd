import pytest

from gtd.config import AppConfig, InboxConfig, parse_config, read_config


@pytest.mark.integration
def test_read_config():
    config = read_config("config.yaml")
    assert isinstance(config, AppConfig)
    assert config.inbox
    for inbox in config.inbox:
        assert isinstance(inbox, InboxConfig)
        assert isinstance(inbox.destination, bool)


def test_destination_defaults_to_false():
    config = parse_config(
        """
        inbox:
          - config:
              kind: org
              path: ~/inbox.org
        """
    )
    assert config.inbox[0].destination is False
    assert config.inbox[0].config.kind == "org"
