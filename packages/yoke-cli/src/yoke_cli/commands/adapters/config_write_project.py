"""Project checkout registration CLI adapter.

Split from :mod:`yoke_cli.commands.adapters.config_write` under the
authored-file line cap; re-exported there so existing imports are unaffected.
"""

from __future__ import annotations

import argparse
from typing import List

from yoke_cli.commands._helpers import parse_or_usage_error
from yoke_cli.commands.adapters.config_write_shared import run
from yoke_cli.commands.session_begin_corroboration import resolve_ambient
from yoke_cli.config import writer
from yoke_contracts.machine_config.schema_projects import (
    reassign_ambient_session_refusal,
)

PROJECT_REGISTER_USAGE = (
    "yoke project register REPO_ROOT --project-id N "
    "[--board-scope SCOPE] [--board-render-path PATH] [--reassign] "
    "[--config PATH]"
)


def project_register(args: List[str]) -> int:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        prog="yoke project register",
        description=(
            "Map one machine-local checkout to a project id, shared by all connections.\n"
            "Moving a project id already routed elsewhere needs --reassign."
        ),
    )
    parser.add_argument("repo_root")
    parser.add_argument("--project-id", dest="project_id", type=int, required=True)
    parser.add_argument("--board-scope", dest="board_scope", default=None)
    parser.add_argument("--board-render-path", dest="board_render_path", default=None)
    parser.add_argument(
        "--reassign",
        action="store_true",
        default=False,
        help="Deliberate setup/operator-authorized checkout move only.",
    )
    parser.add_argument("--config", dest="config_path", default=None)
    parsed = parse_or_usage_error(parser, args, PROJECT_REGISTER_USAGE)
    if parsed is None:
        return 2

    def _register() -> dict:
        if parsed.reassign:
            ambient_session_id = resolve_ambient()
            if ambient_session_id:
                raise writer.MachineConfigWriteError(
                    reassign_ambient_session_refusal(ambient_session_id)
                )
        return writer.register_project(
            parsed.repo_root,
            parsed.project_id,
            board_scope=parsed.board_scope,
            board_render_path=parsed.board_render_path,
            reassign=parsed.reassign,
            path=parsed.config_path,
        )

    return run(_register)


__all__ = ["PROJECT_REGISTER_USAGE", "project_register"]
