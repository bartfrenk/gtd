import pytest

from gtd.core import Item
from gtd.spotify import Config, SpotifyInbox


@pytest.mark.integration
async def test_get_items_reads_real_playlist():
    config = Config.from_env("Inbox")
    inbox = SpotifyInbox.from_config(config)

    items = [item async for item in inbox.get_items()]
    for item in items:
        print(item)
    assert all(isinstance(item, Item) for item in items)
