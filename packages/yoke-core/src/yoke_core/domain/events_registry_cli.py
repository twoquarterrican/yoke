"""Registry subcommands for ``python3 -m yoke_core.domain.events_crud``.

Every subcommand reads: ``event_registry`` rows come from the code event
catalog (:mod:`yoke_core.domain.event_catalog`), which each boot projects
into the table, so a registry change is a catalog edit, not a CLI write.

Lookups go through the ``events_crud`` module attribute so test-time
monkeypatches flow through.
"""

from __future__ import annotations

import os
import sys

from yoke_core.domain import events_crud as _ec

_REG_USAGE = (
    "Usage: events_crud registry <subcommand> [args...]\n"
    "\n"
    "Subcommands:\n"
    "  get <name>\n"
    "  list [--kind K] [--service S]\n"
    "  count\n"
    "  discover\n"
    "  audit\n"
    "  diff [--verbose]\n"
    "\n"
    "Registry rows come from yoke_core/domain/event_catalog.py; edit that\n"
    "table and run python3 -m yoke_core.domain.event_catalog_render."
)


def cli_registry(argv: list[str]) -> int:
    """Parse CLI args for registry subcommands."""
    db_path = os.environ.get("YOKE_DB")
    if not argv:
        print(_REG_USAGE, file=sys.stderr)
        return 2

    sub = argv[0]
    rest = argv[1:]

    if sub == "get":
        return _registry_get(db_path, rest)
    if sub == "list":
        return _registry_list(db_path, rest)
    if sub == "count":
        print(_ec.cmd_registry_count(db_path))
        return 0
    if sub == "discover":
        result = _ec.cmd_registry_discover()
        if result:
            print(result)
        return 0
    if sub == "audit":
        return _registry_audit(db_path)
    if sub == "diff":
        return _registry_diff(db_path, rest)
    print(_REG_USAGE, file=sys.stderr)
    return 2


def _registry_get(db_path: str | None, rest: list[str]) -> int:
    if not rest:
        print("Error: event_name is required", file=sys.stderr)
        return 2
    try:
        print(_ec.cmd_registry_get(db_path, rest[0]))
    except LookupError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def _registry_list(db_path: str | None, rest: list[str]) -> int:
    kwargs: dict[str, str | None] = {"kind": None, "service": None}
    i = 0
    while i < len(rest):
        if rest[i] == "--kind" and i + 1 < len(rest):
            i += 1
            kwargs["kind"] = rest[i]
        elif rest[i] == "--service" and i + 1 < len(rest):
            i += 1
            kwargs["service"] = rest[i]
        else:
            print(f"Error: unknown argument '{rest[i]}'\n{_REG_USAGE}", file=sys.stderr)
            return 2
        i += 1
    result = _ec.cmd_registry_list(db_path, **kwargs)
    if result:
        print(result)
    return 0


def _registry_audit(db_path: str | None) -> int:
    try:
        print(_ec.cmd_registry_audit(db_path))
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def _registry_diff(db_path: str | None, rest: list[str]) -> int:
    try:
        print(_ec.cmd_registry_diff(db_path, verbose="--verbose" in rest))
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0
