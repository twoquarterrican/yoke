"""Linux reset admission: sealed probes, live sign-ins and the fixture desktop."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from yoke_harness.ssh_linux_sign_in_stores import verify_sign_in_stores
from yoke_harness.ssh_mac_baseline_probes import (
    GOLDEN_PROBES_SUFFIX,
    parse_baseline_probes,
)
from yoke_harness.test_machine_types import HostActionResult

# Shared by the read-only admission call and the final check before teardown.
from yoke_harness import linux_desktop_state

DESKTOP_PROGRAM = (
    Path(linux_desktop_state.__file__)
    .read_text()
    .replace("from __future__ import annotations", "")
)


def reset_preflight(control: Any, destination: str) -> HostActionResult:
    """Read the sealed probes, then verify live sign-ins before any cleanup."""
    try:
        document = control.read_remote_text(destination + GOLDEN_PROBES_SUFFIX)
    except RuntimeError:
        return HostActionResult(
            False,
            {"recovery": "Repair the sealed baseline probes file access, then retry."},
            "baseline_probes_unavailable",
        )
    try:
        probes = parse_baseline_probes(document)
    except ValueError:
        return HostActionResult(
            False,
            {
                "recovery": "Repair the sealed baseline probes document before resetting."
            },
            "baseline_probes_invalid",
        )
    return HostActionResult(
        True, {"sign_in_plan": verify_sign_in_stores(control, probes)}
    )
