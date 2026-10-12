"""Warn when the installed CLI is older than the release prod serves.

Every HTTPS response already carries the server's engine version, so the
comparison costs no request of its own. It warns once per process, on stderr,
and never updates or refuses: the machine's prod relay installs each release
it observes prod serving, and this warning is what a machine left behind sees.
"""

from __future__ import annotations

import sys
from typing import TextIO

from yoke_cli.config.operator_cli_release_follow import update_recovery
from yoke_contracts.engine_version import (
    compare_engine_versions,
    local_handshake_version,
)

_warned = False


def warn_if_behind_prod(
    *,
    prod: bool,
    server_version: str,
    local_version: str | None = None,
    stream: TextIO | None = None,
) -> bool:
    """Print one warning when this CLI predates prod's release; True if printed."""
    global _warned
    if _warned or not prod or not server_version:
        return False
    local = local_version if local_version is not None else local_handshake_version()
    if not local or compare_engine_versions(local, server_version) != -1:
        return False
    _warned = True
    served = server_version.strip().removeprefix("v")
    print(
        f"yoke: warning: this CLI ({local}) is older than {served}, the release "
        "prod serves. The prod relay installs each release it observes; it has "
        f"not moved this one yet. To update now, {update_recovery(served)}.",
        file=stream or sys.stderr,
    )
    return True


__all__ = ["warn_if_behind_prod"]
