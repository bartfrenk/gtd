# pyright: reportUnusedCallResult = false
import asyncio
from argparse import ArgumentParser, Namespace
from pathlib import Path


async def run_sync(ns: Namespace) -> None:
    print(ns)


def set_sync_parser(parser: ArgumentParser) -> None:
    parser.add_argument("--output", "-o", type=Path)
    parser.add_argument("--config", "-c", type=Path)
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
