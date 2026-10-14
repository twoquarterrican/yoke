"""Event catalog checks that read this repo's own source tree.

* ``HC-event-callsite-registry-sync`` — every event name a discoverable call
  site in this checkout emits has a row in ``yoke_core.domain.event_catalog``,
  the table every boot projects into ``event_registry``.
* ``HC-event-catalog-drift`` — ``docs/event-catalog.md`` in this checkout is
  the current render of that table.

Both answer a question about the Yoke source tree, so they belong to the
project rather than to every install the engine ships to.
"""

from __future__ import annotations

import os
from typing import Dict

from yoke_core.domain.event_catalog import EVENT_CATALOG
from yoke_core.domain.event_catalog_render import (
    EVENT_CATALOG_RELPATH,
    catalog_appendix,
    render_catalog_text,
)
from yoke_core.domain.events_crud import cmd_registry_discover

import yoke_core.engines.doctor_report as _base
from yoke_core.engines.doctor_report import DoctorArgs, RecordCollector

_RENDER_COMMAND = "python3 -m yoke_core.domain.event_catalog_render"


def hc_event_callsite_registry_sync(
    conn, args: DoctorArgs, rec: RecordCollector
) -> None:
    """HC-event-callsite-registry-sync: every call site has a catalog row."""
    repo_root = _base._resolve_repo_root()
    if not repo_root:
        rec.record(
            "HC-event-callsite-registry-sync",
            "Event call site registry sync",
            "PASS",
            "Cannot resolve repo root, skipping",
        )
        return

    missing: Dict[str, str] = {}
    for line in cmd_registry_discover(repo_root).splitlines():
        name, _, path = line.partition("|")
        if name and name not in EVENT_CATALOG:
            missing.setdefault(name, path)

    if missing:
        rec.record(
            "HC-event-callsite-registry-sync",
            "Event call site registry sync",
            "WARN",
            "Emitted names without an event_catalog.py row (add the row, then run "
            f"{_RENDER_COMMAND}):\n"
            + "\n".join(f"- {name} ({path})" for name, path in sorted(missing.items())),
        )
    else:
        rec.record(
            "HC-event-callsite-registry-sync",
            "Event call site registry sync",
            "PASS",
            "",
        )


def hc_event_catalog_drift(conn, args: DoctorArgs, rec: RecordCollector) -> None:
    """HC-event-catalog-drift: the committed catalog doc is the current render."""
    repo_root = _base._resolve_repo_root()
    if not repo_root:
        rec.record(
            "HC-event-catalog-drift",
            "Event catalog drift",
            "PASS",
            "Cannot resolve repo root, skipping",
        )
        return

    catalog_path = os.path.join(repo_root, EVENT_CATALOG_RELPATH)
    try:
        with open(catalog_path, "r") as handle:
            committed = handle.read()
    except OSError as exc:
        rec.record(
            "HC-event-catalog-drift",
            "Event catalog drift",
            "WARN",
            f"Cannot read {catalog_path}: {exc}. Run: {_RENDER_COMMAND}",
        )
        return

    if committed != render_catalog_text(catalog_appendix(committed)):
        rec.record(
            "HC-event-catalog-drift",
            "Event catalog drift",
            "WARN",
            f"{EVENT_CATALOG_RELPATH} does not match event_catalog.py. "
            f"Regenerate: {_RENDER_COMMAND}",
        )
    else:
        rec.record(
            "HC-event-catalog-drift",
            "Event catalog drift",
            "PASS",
            f"{len(EVENT_CATALOG)} catalog events rendered",
        )


__all__ = ["hc_event_callsite_registry_sync", "hc_event_catalog_drift"]

# Slug and display name are the ones this check has always reported under.
from yoke_project_checks._declare import (  # noqa: E402
    self_project_checks,
)

PROJECT_HEALTH_CHECKS = self_project_checks(
    (
        "event-callsite-registry-sync",
        "Event call site registry sync",
        hc_event_callsite_registry_sync,
    ),
    ("event-catalog-drift", "Event catalog drift", hc_event_catalog_drift),
)
