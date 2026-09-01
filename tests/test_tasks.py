import os

import pytest

from gtd.core import Item
from gtd.tasks import TasksInbox, Config


@pytest.mark.integration
async def test_get_items_reads_real_tasklist():
    config = Config.from_env("Inbox")
    inbox = TasksInbox.from_config(config)

    items = [item async for item in inbox.get_items()]
    for item in items:
        print(item)
    assert all(isinstance(item, Item) for item in items)
