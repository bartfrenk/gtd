# pyright: reportUnusedCallResult = false
import asyncio
from argparse import SUPPRESS, ArgumentParser, Namespace
from pathlib import Path

from gtd.config import build_inbox, read_config
from gtd.core import OPEN_STATUSES, init_logging, log


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
            log.info("No items in %s", source)
            continue

        log.info("Moving %d items from %s to %s", len(items), source, destination)
        await destination.add(items)
        await source.clear()


DEFAULT_CONFIG_PATH = Path.home() / ".config/gtd/config.yaml"


def set_sync_parser(parser: ArgumentParser) -> None:
    parser.add_argument("--config", "-c", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.set_defaults(run=run_sync)


def create_parser() -> ArgumentParser:
    debug_parser = ArgumentParser(add_help=False)
    debug_parser.add_argument("--debug", action="store_true", default=SUPPRESS)

    parser = ArgumentParser(parents=[debug_parser])

    subparsers = parser.add_subparsers()
    set_sync_parser(subparsers.add_parser("sync", parents=[debug_parser]))
    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()
    init_logging(getattr(args, "debug", False))
    if hasattr(args, "run"):
        asyncio.run(args.run(args))  # pyright: ignore[reportAny]


if __name__ == "__main__":
    main()
