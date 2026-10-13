"""Name guards the hook deadline skipped so a silent hole is visible."""

from __future__ import annotations

import sys

from yoke_contracts.hook_diagnostics import format_hook_diagnostic

from typing import Optional

from yoke_core.hooks.remote_policy import RunControls


def record_skipped_guards(
    skipped: list[str],
    controls: Optional[RunControls],
) -> None:
    marker = f"deadline_skipped:{len(skipped)}:{','.join(skipped)}"
    if controls is not None:
        controls.degraded.append(marker)
    print(
        format_hook_diagnostic(
            "hook runner",
            f"deadline exhausted; skipped {len(skipped)} guards: "
            f"{', '.join(skipped)}; retry the action to reevaluate the skipped guards",
        ),
        file=sys.stderr,
    )
