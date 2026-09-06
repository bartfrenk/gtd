# pyright: reportUnusedCallResult = false
import asyncio
from argparse import ArgumentParser, Namespace
from pathlib import Path

from gtd.config import build_inbox, read_config
from gtd.core import OPEN_STATUSES


async def run_sync(ns: Namespace) -> None:
    config = read_config(ns.config)  # pyright: ignore[reportAny]
    inboxes = [(inbox_config, build_inbox(inbox_config.config)) for inbox_config in config.inbox]

    destinations = [inbox for inbox_config, inbox in inboxes if inbox_config.destination]
    if len(destinations) != 1:
        raise ValueError(f"Expected exactly one destination inbox, found {len(destinations)}")
    destination = destinations[0]

    for inbox_config, source in inboxes:
        if inbox_config.destination:
            continue
        items = [item async for item in source.get_items(status=set(OPEN_STATUSES))]
        if not items:
            continue
        await destination.add(items)
        await source.clear()


def set_sync_parser(parser: ArgumentParser) -> None:
    parser.add_argument("--config", "-c", type=Path, required=True)
    parser.set_defaults(run=run_sync)


def create_parser() -> ArgumentParser:
    parser = ArgumentParser()

    subparsers = parser.add_subparsers()
    set_sync_parser(subparsers.add_parser("sync"))
    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()
    if hasattr(args, "run"):
        asyncio.run(args.run(args))  # pyright: ignore[reportAny]
