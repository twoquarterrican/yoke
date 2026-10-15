"""Preserve uncertain deployment writes until their durable owner answers."""

from functools import wraps
import sys
from yoke_cli.transport.relay_telemetry import TRANSPORT_FAILED_CODE
from yoke_core.domain.function_connection_loss import CONNECTION_LOST_CODE

UNKNOWN_CODES = frozenset({TRANSPORT_FAILED_CODE, CONNECTION_LOST_CODE})


class DeploymentOutcomeUnknown(RuntimeError):
    """No authoritative answer; never settle this attempt as failed or retry it."""

    def __init__(self, run_id, function_id, request_id, detail):
        self.code = "deployment_outcome_unknown"
        super().__init__(
            f"{self.code}: {function_id} request {request_id or 'unreported'} on run {run_id} "
            f"has no confirmed outcome: {detail}. No retry or failure transition was issued. "
            f"Read `yoke deployment-runs get {run_id}` and the driver's capture; wait for "
            "the preparation receipt or reconcile the existing provider attempt before re-driving "
            "this same run. Do not use --fresh for response loss."
        )


def preserve_unknown_outcome(function):
    """Stop the driver without changing a pending receipt or run status."""

    @wraps(function)
    def run(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except DeploymentOutcomeUnknown as exc:
            print(str(exc), file=sys.stderr, flush=True)
            return 1

    return run
