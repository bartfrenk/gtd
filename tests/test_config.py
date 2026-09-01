import pytest
from pydantic import ValidationError

from gtd.config import AppConfig, read_config


@pytest.mark.integration
def test_read_config():
    config = read_config("config.yaml")
    assert isinstance(config, AppConfig)
