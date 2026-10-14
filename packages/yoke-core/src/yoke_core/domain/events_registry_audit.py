"""Registry audit and codebase-diff reporting for the Yoke event platform.

Owns the read-only reporting queries that combine the ``event_registry``
and ``events`` tables with the codebase discovery surface to produce:

- ``cmd_registry_audit``: a multi-section audit report (stale, rogue,
  unregistered call sites).
- ``cmd_registry_diff``: a registry-vs-codebase diff (``+`` discovered
  but not registered, ``-`` registered but no discoverable call site,
  optional ``=`` match lines under ``verbose``).

Rogue names — emitted but absent from the registry, which every boot
makes equal to the code event catalog — are the drift signal for an
emitter that lacks its catalog row.

Both functions perform a runtime
``import yoke_core.domain.events_crud as _crud`` so that test-time
patches of ``events_crud.cmd_registry_discover`` flow through. The
late-import pattern is intentional and must not be collapsed to a
top-level ``from .events_registry_discovery import cmd_registry_discover``
— that would bypass the re-export and break tests that patch the
``events_crud`` symbol.
"""

from __future__ import annotations

from typing import Optional

from yoke_core.domain.db_helpers import connect, query_rows, query_scalar
from yoke_core.domain.schema_common import _table_exists
from yoke_core.domain.time_sql import now_sql

__all__ = [
    "cmd_registry_audit",
    "cmd_registry_diff",
]


def cmd_registry_audit(
    db_path: Optional[str] = None, repo_root: Optional[str] = None
) -> str:
    """Combined registry health report."""
    # Late import: ``events_crud`` re-exports from this module, so a top-level
    # ``from .events_crud import _now_iso`` would re-enter a partially-initialised
    # ``events_crud`` whenever a caller imports ``events_registry_audit`` directly.
    # Importing the module via ``events_crud`` here also lets tests patch
    # ``events_crud.cmd_registry_discover`` and have audit see the patched name.
    import yoke_core.domain.events_crud as _crud

    _now_iso = _crud._now_iso

    conn = connect(db_path)
    try:
        has_reg = _table_exists(conn, "event_registry")
        has_evt = _table_exists(conn, "events")
        if not has_reg or not has_evt:
            raise RuntimeError(
                f"required tables missing (event_registry={has_reg}, events={has_evt})"
            )

        lines: list[str] = [
            "## Event Registry Audit",
            f"Generated: {_now_iso()}",
            "",
        ]

        # 1. Stale entries
        lines.append("### Stale Entries (registered, never emitted in 30d)")
        stale = query_rows(
            conn,
            "SELECT r.event_name, r.owner_service FROM event_registry r "
            "WHERE r.event_name NOT IN ("
            "  SELECT DISTINCT event_name FROM events "
            f"  WHERE created_at >= {now_sql(offset_days=-30)}"
            ") ORDER BY r.event_name ASC",
        )
        if not stale:
            lines.append("(none)")
        else:
            for row in stale:
                lines.append(f"- {row['event_name']} (service: {row['owner_service']})")
        lines.append("")

        # 2. Rogue events
        lines.append("### Rogue Events (emitted, not registered)")
        rogue = query_rows(
            conn,
            "SELECT DISTINCT e.event_name FROM events e "
            f"WHERE e.created_at >= {now_sql(offset_days=-30)} "
            "AND e.event_name NOT IN (SELECT event_name FROM event_registry) "
            "ORDER BY e.event_name ASC",
        )
        if not rogue:
            lines.append("(none)")
        else:
            for row in rogue:
                lines.append(f"- {row['event_name']}")
        lines.append("")

        # 3. Unregistered call sites
        lines.append("### Unregistered Call Sites (in codebase, not in registry)")
        try:
            discovered_raw = _crud.cmd_registry_discover(repo_root)
        except Exception:
            discovered_raw = ""

        discovered_pairs: list[tuple[str, str]] = []
        if discovered_raw:
            for dline in discovered_raw.split("\n"):
                if "|" in dline:
                    parts = dline.split("|", 1)
                    discovered_pairs.append((parts[0], parts[1]))

        unreg_lines: list[str] = []
        for dname, dfile in discovered_pairs:
            in_reg = query_scalar(
                conn,
                "SELECT COUNT(*) FROM event_registry WHERE event_name=%s",
                (dname,),
            )
            if in_reg == 0:
                unreg_lines.append(f"- {dname} (file: {dfile})")

        if not unreg_lines:
            lines.append("(none)")
        else:
            lines.extend(unreg_lines)
        lines.append("")

        # Summary
        lines.append("### Summary")
        lines.append(
            f"{len(stale)} stale, {len(rogue)} rogue, {len(unreg_lines)} unregistered"
        )

        return "\n".join(lines)
    finally:
        conn.close()


def cmd_registry_diff(
    db_path: Optional[str] = None,
    repo_root: Optional[str] = None,
    verbose: bool = False,
) -> str:
    """Registry vs codebase diff."""
    # Import via events_crud so tests that patch events_crud.cmd_registry_discover work.
    import yoke_core.domain.events_crud as _crud

    conn = connect(db_path)
    try:
        if not _table_exists(conn, "event_registry"):
            raise RuntimeError("event_registry table not found")

        try:
            discovered_raw = _crud.cmd_registry_discover(repo_root)
        except Exception:
            discovered_raw = ""

        # Build discovered name -> file map
        disc_map: dict[str, str] = {}
        if discovered_raw:
            for dline in discovered_raw.split("\n"):
                if "|" in dline:
                    parts = dline.split("|", 1)
                    if parts[0] not in disc_map:
                        disc_map[parts[0]] = parts[1]

        disc_names = set(disc_map.keys())

        reg_rows = query_rows(
            conn,
            "SELECT event_name FROM event_registry ORDER BY event_name ASC",
        )
        reg_names = {row["event_name"] for row in reg_rows}

        diff_lines: list[str] = []
        diff_count = 0

        # + lines: discovered but not in registry
        for dname in sorted(disc_names):
            all_reg = query_scalar(
                conn,
                "SELECT COUNT(*) FROM event_registry WHERE event_name=%s",
                (dname,),
            )
            if all_reg == 0:
                diff_lines.append(f"+ {dname} (discovered in {disc_map[dname]})")
                diff_count += 1
            elif verbose:
                diff_lines.append(f"= {dname}")

        # - lines: in registry but no call site
        for rname in sorted(reg_names):
            if rname not in disc_names:
                diff_lines.append(f"- {rname} (in registry, no call site found)")
                diff_count += 1

        if diff_count == 0 and not verbose:
            return "Registry is in sync with codebase. 0 differences."
        elif diff_count == 0 and verbose:
            result = "Registry is in sync with codebase. 0 differences."
            if diff_lines:
                result += "\n" + "\n".join(diff_lines)
            return result
        else:
            return "\n".join(diff_lines)
    finally:
        conn.close()
