"""Which environment row a QA execution-target rebind resolves to.

A snapshot that recorded its environment id answers for itself. Otherwise
the requirement's own ``target_env`` names the environment it proves, so a
stage source on a plan whose default target is production rebinds to stage.
Only then does the plan default, and finally the snapshot's site and
environment names, decide.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from yoke_core.domain.db_helpers import query_one, query_rows
from yoke_core.domain.qa_requirement_rebind_identity import (
    QaRebindError,
    _int,
    _mapping,
)
from yoke_core.domain.schema_common import _table_exists


def environment_row(conn: Any, environment_id: int) -> dict[str, Any] | None:
    if not _table_exists(conn, "environments"):
        return None
    row = query_one(
        conn,
        "SELECT e.id AS environment_id, e.name AS environment_name, e.url, "
        "e.settings, s.name AS site_name FROM environments e "
        "JOIN sites s ON s.id=e.site WHERE e.id=%s",
        (int(environment_id),),
    )
    return dict(row) if row is not None else None


def _row_id(row: Any) -> int:
    if hasattr(row, "keys"):
        return int(row["id"])
    return int(row[0])


def _one_named(rows: list[Any], *, site: str, name: str) -> int:
    if len(rows) == 1:
        return _row_id(rows[0])
    if len(rows) > 1:
        raise QaRebindError(
            f"site {site!r} and environment {name!r} resolve to {len(rows)} "
            "rows; start a fresh execution or use sanctioned retirement or "
            "supersession"
        )
    raise QaRebindError(
        f"no environment row named {site}/{name}; start a fresh execution "
        "or use sanctioned retirement or supersession"
    )


def _plan_target_id(conn: Any, plan_id: int | None) -> int:
    if not plan_id:
        return 0
    plan = query_one(
        conn, "SELECT target_environment_id FROM qa_plans WHERE id=%s", (int(plan_id),)
    )
    return 0 if plan is None else _int(plan["target_environment_id"])


def _declared_target_id(
    conn: Any, stored: Mapping[str, Any], *, plan_target: int, target_env: str
) -> int:
    """The requirement's ``target_env`` on the snapshot's site, else the plan's."""
    site_name = str(_mapping(stored.get("site")).get("name") or "")
    if site_name:
        rows = query_rows(
            conn,
            "SELECT e.id FROM environments e JOIN sites s ON s.id=e.site "
            "WHERE s.name=%s AND e.name=%s",
            (site_name, target_env),
        )
        return _one_named(rows, site=site_name, name=target_env)
    if not plan_target:
        return 0
    rows = query_rows(
        conn,
        "SELECT e.id FROM environments e JOIN environments p ON p.site=e.site "
        "WHERE p.id=%s AND e.name=%s",
        (plan_target, target_env),
    )
    plan_row = environment_row(conn, plan_target) or {}
    return _one_named(rows, site=str(plan_row.get("site_name") or ""), name=target_env)


def resolve_live_environment_id(
    conn: Any,
    stored: Mapping[str, Any],
    *,
    plan_id: int | None,
    target_env: str = "",
) -> tuple[int, str]:
    """Pick the row: stored id, requirement target, plan target, site and name."""
    stored_id = _int(_mapping(stored.get("environment")).get("id"))
    if stored_id:
        return stored_id, "stored environment.id"
    plan_target = _plan_target_id(conn, plan_id)
    if target_env:
        declared = _declared_target_id(
            conn, stored, plan_target=plan_target, target_env=target_env
        )
        if declared:
            return declared, "qa_requirements.target_env"
    if plan_target:
        return plan_target, "qa_plans.target_environment_id"
    site_name = str(_mapping(stored.get("site")).get("name") or "")
    env_name = str(_mapping(stored.get("environment")).get("name") or "")
    if site_name and env_name:
        rows = query_rows(
            conn,
            "SELECT e.id FROM environments e JOIN sites s ON s.id=e.site "
            "WHERE s.name=%s AND e.name=%s",
            (site_name, env_name),
        )
        return _one_named(rows, site=site_name, name=env_name), (
            "stored site.name and environment.name"
        )
    raise QaRebindError(
        "stored target records no environment identity; start a fresh "
        "deployment/plan execution or use sanctioned retirement or "
        "supersession"
    )


__all__ = ["environment_row", "resolve_live_environment_id"]
