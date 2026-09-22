from __future__ import annotations

from argparse import Namespace
from collections.abc import AsyncIterator
from pathlib import Path
from typing import final, override

import pytest

from gtd import org, spotify, tasks
from gtd.__main__ import run_auth_config, run_sync
from gtd.config import AppConfig, InboxConfig
from gtd.core import Inbox, Item, Status


@final
class FakeInbox(Inbox):
    def __init__(self, items: list[Item] | None = None) -> None:
        self.items = items or []
        self.added: list[Item] = []
        self.cleared = False

    @override
    async def get_items(self, status: set[Status] | None = None) -> AsyncIterator[Item]:
        for item in self.items:
            if status is None or item.status in status:
                yield item

    @override
    async def add(self, items: list[Item]) -> None:
        self.added.extend(items)

    @override
    async def clear(self) -> None:
        self.cleared = True


def _config(path: str) -> org.Config:
    return org.Config(path=Path(path))


def _setup(monkeypatch, inboxes: list[tuple[InboxConfig, FakeInbox]]) -> None:
    app_config = AppConfig(inbox=[inbox_config for inbox_config, _ in inboxes])
    by_id = {id(inbox_config.config): fake for inbox_config, fake in inboxes}

    async def fake_read_config(_) -> AppConfig:
        return app_config

    monkeypatch.setattr("gtd.__main__.read_config", fake_read_config)
    monkeypatch.setattr("gtd.__main__.build_inbox", lambda config: by_id[id(config)])


async def test_run_sync_merges_open_items_and_clears_sources(monkeypatch):
    source1 = FakeInbox([Item(title="a", status=Status.TODO), Item(title="b", status=Status.DONE)])
    source2 = FakeInbox([Item(title="c", status=Status.NEXT)])
    destination = FakeInbox()

    inboxes = [
        (InboxConfig(config=_config("s1"), destination=False), source1),
        (InboxConfig(config=_config("s2"), destination=False), source2),
        (InboxConfig(config=_config("dest"), destination=True), destination),
    ]
    _setup(monkeypatch, inboxes)

    await run_sync(Namespace(config=Path("unused.yaml")))

    assert {item.title for item in destination.added} == {"a", "c"}
    assert source1.cleared is True
    assert source2.cleared is True
    assert destination.cleared is False


async def test_run_sync_skips_add_and_clear_when_no_open_items(monkeypatch):
    source = FakeInbox([Item(title="done", status=Status.DONE)])
    destination = FakeInbox()

    inboxes = [
        (InboxConfig(config=_config("s1"), destination=False), source),
        (InboxConfig(config=_config("dest"), destination=True), destination),
    ]
    _setup(monkeypatch, inboxes)

    await run_sync(Namespace(config=Path("unused.yaml")))

    assert destination.added == []
    assert source.cleared is False


async def test_run_sync_raises_when_no_destination(monkeypatch):
    source = FakeInbox([Item(title="a", status=Status.TODO)])

    inboxes = [(InboxConfig(config=_config("s1"), destination=False), source)]
    _setup(monkeypatch, inboxes)

    with pytest.raises(ValueError, match="Expected exactly one destination inbox, found 0"):
        await run_sync(Namespace(config=Path("unused.yaml")))


async def test_run_sync_raises_when_multiple_destinations(monkeypatch):
    dest1 = FakeInbox()
    dest2 = FakeInbox()

    inboxes = [
        (InboxConfig(config=_config("d1"), destination=True), dest1),
        (InboxConfig(config=_config("d2"), destination=True), dest2),
    ]
    _setup(monkeypatch, inboxes)

    with pytest.raises(ValueError, match="Expected exactly one destination inbox, found 2"):
        await run_sync(Namespace(config=Path("unused.yaml")))


def _setup_auth_config(monkeypatch, app_config: AppConfig) -> None:
    async def fake_read_config(_) -> AppConfig:
        return app_config

    monkeypatch.setattr("gtd.__main__.read_config", fake_read_config)


async def test_run_auth_config_skips_inboxes_with_valid_tokens(monkeypatch, capsys):
    task_config = tasks.Config(
        title="Inbox", client_id="cid", client_secret="csec", refresh_token="good"
    )
    app_config = AppConfig(inbox=[InboxConfig(config=task_config)])
    _setup_auth_config(monkeypatch, app_config)
    monkeypatch.setattr(tasks.Config, "is_valid", lambda self: True)

    def fail_reauthorize(self):
        raise AssertionError("reauthorize should not be called for a valid token")

    monkeypatch.setattr(tasks.Config, "reauthorize", fail_reauthorize)

    await run_auth_config(Namespace(config=Path("unused.yaml")))

    assert capsys.readouterr().out == ""


async def test_run_auth_config_reauthorizes_and_prints_invalid_tokens(monkeypatch, capsys):
    task_config = tasks.Config(
        title="Inbox", client_id="cid", client_secret="csec", refresh_token="dead"
    )
    spotify_config = spotify.Config(
        playlist_id="pid", client_id="cid2", client_secret="csec2", refresh_token="dead"
    )
    app_config = AppConfig(
        inbox=[
            InboxConfig(config=task_config),
            InboxConfig(config=spotify_config),
            InboxConfig(config=org.Config(path=Path("/tmp/unused.org"))),
        ]
    )
    _setup_auth_config(monkeypatch, app_config)
    monkeypatch.setattr(tasks.Config, "is_valid", lambda self: False)
    monkeypatch.setattr(spotify.Config, "is_valid", lambda self: False)
    monkeypatch.setattr(tasks.Config, "reauthorize", lambda self: "new-tasks-token")
    monkeypatch.setattr(spotify.Config, "reauthorize", lambda self: "new-spotify-token")

    await run_auth_config(Namespace(config=Path("unused.yaml")))

    out = capsys.readouterr().out
    assert "tasks:Inbox: new-tasks-token" in out
    assert "spotify:pid: new-spotify-token" in out
