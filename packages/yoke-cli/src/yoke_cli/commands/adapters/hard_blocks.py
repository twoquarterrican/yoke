"""Public dependency gate evaluation over the selected control plane."""

from __future__ import annotations

import argparse

from yoke_cli.commands._helpers import (
    add_json_arg,
    add_session_arg,
    dispatch_and_emit,
    item_target,
    parse_or_usage_error,
)

USAGE = "yoke advance preflight hard-blocks PREFIX-N [--gate-point POINT] [--json]"


def hard_blocks(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="yoke advance preflight hard-blocks")
    parser.add_argument("item")
    parser.add_argument(
        "--gate-point",
        choices=("activation", "integration", "closure"),
        default="activation",
    )
    add_session_arg(parser)
    add_json_arg(parser)
    parsed = parse_or_usage_error(parser, args, USAGE)
    if parsed is None:
        return 2

    def writer(response, stdout, stderr):
        for blocker in (response.result or {}).get("blockers", []):
            print(blocker, file=stdout)

    verdict = {}

    def remember(response, actor):
        verdict.update(response.result or {})
        return response

    code = dispatch_and_emit(
        function_id="advance.preflight.hard_blocks",
        target=item_target("item", parsed.item, parsed.project),
        payload={"gate_filter": parsed.gate_point},
        session_id=parsed.session_id,
        json_mode=parsed.json_mode,
        human_writer=writer,
        response_recovery=remember,
    )
    return code or (1 if verdict.get("blockers") else 0)
