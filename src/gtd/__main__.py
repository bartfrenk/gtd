# pyright: reportUnusedCallResult = false
import asyncio
from argparse import SUPPRESS, ArgumentParser, Namespace
from collections.abc import Callable
from pathlib import Path

from gtd import org, spotify, tasks
from gtd.config import build_inbox, read_config
from gtd.core import OPEN_STATUSES, init_logging, log


async def run_sync(ns: Namespace) -> None:
    config = await read_config(ns.config)  # pyright: ignore[reportAny]
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


AUTH_FLOWS: dict[str, Callable[[], None]] = {
    "tasks": tasks.authorize,
    "spotify": spotify.authorize,
}


async def run_auth(ns: Namespace) -> None:
    AUTH_FLOWS[ns.inbox]()  # pyright: ignore[reportAny]


def set_auth_inbox_parser(parser: ArgumentParser, inbox: str) -> None:
    parser.set_defaults(run=run_auth, inbox=inbox)


def _renew_if_invalid(label: str, config: tasks.Config | spotify.Config) -> None:
    if config.is_valid():
        log.info("Refresh token for %s is still valid", label)
        return
    log.warning("Refresh token for %s is invalid or expired; reauthorizing", label)
    print(f"{label}: {config.reauthorize()}")


async def run_auth_config(ns: Namespace) -> None:
    config = await read_config(ns.config)  # pyright: ignore[reportAny]
    for inbox_config in config.inbox:
        inbox = inbox_config.config
        match inbox:
            case tasks.Config():
                _renew_if_invalid(f"tasks:{inbox.title}", inbox)
            case spotify.Config():
                _renew_if_invalid(f"spotify:{inbox.playlist_id}", inbox)
            case org.Config():
                pass


def set_auth_config_parser(parser: ArgumentParser) -> None:
    parser.add_argument("--config", "-c", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.set_defaults(run=run_auth_config)


def set_auth_parser(parser: ArgumentParser, debug_parser: ArgumentParser) -> None:
    subparsers = parser.add_subparsers(required=True)
    for inbox in sorted(AUTH_FLOWS):
        set_auth_inbox_parser(subparsers.add_parser(inbox, parents=[debug_parser]), inbox)
    set_auth_config_parser(subparsers.add_parser("config", parents=[debug_parser]))


def create_parser() -> ArgumentParser:
    debug_parser = ArgumentParser(add_help=False)
    debug_parser.add_argument("--debug", action="store_true", default=SUPPRESS)

    parser = ArgumentParser(parents=[debug_parser])

    subparsers = parser.add_subparsers()
    set_sync_parser(subparsers.add_parser("sync", parents=[debug_parser]))
    set_auth_parser(subparsers.add_parser("auth", parents=[debug_parser]), debug_parser)
    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()
    init_logging(getattr(args, "debug", False))
    if hasattr(args, "run"):
        asyncio.run(args.run(args))  # pyright: ignore[reportAny]


if __name__ == "__main__":
    main()
