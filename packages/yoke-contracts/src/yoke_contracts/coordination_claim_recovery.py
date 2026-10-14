"""Canonical release commands for a held coordination claim.

The holder releases its own claim; a steering seat recovers one stranded
by another session.
"""

from __future__ import annotations

import shlex

from yoke_contracts.coordination_claim_keys import QA_HOST_KEY_PREFIX


OPERATOR_RELEASE_USAGE = (
    "yoke coordination-claim release [--project P] --key K --claim-id N "
    "--holder-session-id S --reason R [--json]"
)
OPERATOR_RELEASE_REASON_EXAMPLE = "stale holder confirmed"
HOLDER_RELEASE_REASON_EXAMPLE = "work finished"


def holder_release_command(
    claim_id: int, *, reason: str = HOLDER_RELEASE_REASON_EXAMPLE
) -> str:
    """Render the holder's own release, which also advances any waiting line."""
    return (
        f"yoke claims coordination-claim release --claim-id {int(claim_id)} "
        f"--reason {shlex.quote(str(reason))}"
    )


def operator_release_command(
    project: str | int | None,
    key: str,
    *,
    claim_id: int,
    holder_session_id: str,
    reason: str = OPERATOR_RELEASE_REASON_EXAMPLE,
) -> str:
    """Render the runnable steering-seat recovery command for one claim."""
    project_args = (
        ()
        if key.startswith(QA_HOST_KEY_PREFIX)
        else (
            "--project",
            shlex.quote(str(project)),
        )
    )
    return " ".join(
        (
            "yoke coordination-claim release",
            *project_args,
            "--key",
            shlex.quote(str(key)),
            "--claim-id",
            str(int(claim_id)),
            "--holder-session-id",
            shlex.quote(str(holder_session_id)),
            "--reason",
            shlex.quote(str(reason)),
        )
    )


__all__ = [
    "HOLDER_RELEASE_REASON_EXAMPLE",
    "OPERATOR_RELEASE_REASON_EXAMPLE",
    "OPERATOR_RELEASE_USAGE",
    "holder_release_command",
    "operator_release_command",
]
