"""Block on one consumer workflow run, saying so before the quiet starts.

The release tools capture the ``yoke github-actions wait-run`` child's output
to parse its verdict, so its per-poll lines never reach the CI log. The
announcement is what tells a reader of that log the step is waiting by design.
"""

from __future__ import annotations

from typing import Callable, Tuple

from yoke_cli.commands.adapters.github_actions_run_wait import (
    RUN_WAIT_POLL_INTERVAL_SEC,
)
from yoke_contracts.designed_wait import announce_designed_wait, poll_every

#: ``(argv, *, timeout) -> (exit code, stdout, stderr)`` for one ``yoke`` call.
YokeRunner = Callable[..., Tuple[int, str, str]]


def wait_run(
    yoke: YokeRunner,
    *,
    repo: str,
    project: str,
    run_id: str,
    timeout_sec: int,
    grace_sec: int,
    purpose: str,
) -> Tuple[int, str, str]:
    """Run ``wait-run`` for *run_id*; *grace_sec* covers the child's own exit."""
    announce_designed_wait(
        f"{purpose} (run {run_id} in {repo})",
        max_wait_seconds=timeout_sec,
        cadence=poll_every(RUN_WAIT_POLL_INTERVAL_SEC),
    )
    argv = ["github-actions", "wait-run", repo, run_id, "--project", project]
    argv += ["--timeout", str(timeout_sec), "--json"]
    return yoke(argv, timeout=timeout_sec + grace_sec)


__all__ = ["wait_run"]
