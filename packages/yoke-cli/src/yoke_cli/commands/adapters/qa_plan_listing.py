"""Paged summary rows for the QA plan catalog."""

from __future__ import annotations

import argparse
from yoke_cli.transport.human_values import write_human

from yoke_cli.commands._helpers import (
    add_full_arg,
    add_json_arg,
    add_session_arg,
    detail_of,
    dispatch_and_emit,
    parse_or_usage_error,
)
from yoke_contracts.api.function_call import TargetRef


USAGE = "yoke qa plan list --project P [--limit N] [--offset N] [--full] [--json]"


def qa_plan_list(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="yoke qa plan list", description=USAGE)
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--limit", type=int, help="Page size (default: 25; maximum: 500)."
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Start at this row of the stable project/slug order.",
    )
    add_full_arg(
        parser,
        "all plans with descriptions, attachments and execution targets unless --limit is named",
    )
    add_session_arg(parser)
    add_json_arg(parser)
    parsed = parse_or_usage_error(parser, args, USAGE)
    if parsed is None:
        return 2
    return dispatch_and_emit(
        function_id="qa.plan.list",
        target=TargetRef(kind="global"),
        payload={
            "project": parsed.project,
            "limit": parsed.limit,
            "offset": parsed.offset,
            "detail": detail_of(parsed),
        },
        session_id=parsed.session_id,
        json_mode=parsed.json_mode,
        human_writer=write_plan_rows,
    )


def write_plan_rows(response, stdout, stderr) -> None:
    write_human(response.result or {}, stdout)
