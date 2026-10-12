"""Read or set the universe-wide order of Cursor's two monthly pools."""

import argparse
from yoke_cli.commands._helpers import (
    add_json_arg,
    add_session_arg,
    dispatch_and_emit,
    parse_or_usage_error,
)
from yoke_contracts.api.function_call import TargetRef

GET = "universe.cursor_quota_order.get"
SET = "universe.cursor_quota_order.set"
USAGE_BY_FUNCTION_ID = {
    GET: "yoke universe cursor-quota-order get [--json]",
    SET: "yoke universe cursor-quota-order set --pool NAME --pool NAME [--json]",
}


def _write(response, stdout, stderr):
    if response.success:
        for index, pool in enumerate((response.result or {}).get("pools", []), start=1):
            stdout.write(f"{index}. {pool}\n")


def _run(args, *, setting):
    function_id = SET if setting else GET
    parser = argparse.ArgumentParser(
        prog="yoke universe cursor-quota-order " + ("set" if setting else "get"),
        description="Universe-wide monthly Cursor pool order. Name Cursor Models and Other Models once each, in consumption order. Empty or blocked candidates are skipped before headroom.",
    )
    if setting:
        parser.add_argument(
            "--pool",
            action="append",
            required=True,
            help="Monthly scope in consumption order; repeat exactly twice.",
        )
    add_json_arg(parser)
    add_session_arg(parser)
    parsed = parse_or_usage_error(parser, args, USAGE_BY_FUNCTION_ID[function_id])
    if parsed is None:
        return 2
    return dispatch_and_emit(
        function_id=function_id,
        target=TargetRef(kind="global"),
        payload={"pools": parsed.pool} if setting else {},
        session_id=parsed.session_id,
        json_mode=parsed.json_mode,
        human_writer=_write,
    )


def get(args):
    return _run(args, setting=False)


def set_order(args):
    return _run(args, setting=True)
