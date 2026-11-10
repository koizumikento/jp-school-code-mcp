import asyncio
import json
import sys
from argparse import SUPPRESS, ArgumentParser
from collections.abc import Sequence

import httpx

from .client import compare_school_records, get_school, refresh_cache, search_schools


def run_cli(argv: Sequence[str]) -> None:
    parser = ArgumentParser(prog="jp-school-code-mcp")
    commands = parser.add_subparsers(required=True)

    command = commands.add_parser("search-schools", argument_default=SUPPRESS)
    command.add_argument("--name")
    command.add_argument("--prefecture")
    command.add_argument("--school-type")
    command.add_argument("--operator-category", choices=["1", "2", "3"])
    command.add_argument("--limit", type=int)
    command.add_argument("--offset", type=int)
    command.set_defaults(handler=search_schools)

    command = commands.add_parser("get-school", argument_default=SUPPRESS)
    command.add_argument("--school-code", required=True)
    command.add_argument("--as-of")
    command.set_defaults(handler=get_school)

    command = commands.add_parser("compare-school-records", argument_default=SUPPRESS)
    command.add_argument("--school-code", required=True)
    command.add_argument("--from-date", required=True)
    command.add_argument("--to-date", required=True)
    command.set_defaults(handler=compare_school_records)

    command = commands.add_parser("refresh", argument_default=SUPPRESS)
    command.set_defaults(handler=refresh_cache)

    arguments = vars(parser.parse_args(argv))
    handler = arguments.pop("handler")
    try:
        result = asyncio.run(handler(**arguments))
    except (ValueError, OSError, httpx.HTTPError) as exc:
        parser.exit(1, f"{parser.prog}: {exc}\n")
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
