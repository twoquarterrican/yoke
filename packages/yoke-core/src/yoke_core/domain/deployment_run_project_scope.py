"""Select whole runs by the projects represented in their membership."""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from yoke_core.domain import db_backend


def run_project_scope(
    conn: Any, project_ids: Collection[int] | None
) -> tuple[list[str], list[int]]:
    """Match a member's project, or an itemless run's owning project."""
    if project_ids is None:
        return [], []
    ids = sorted({int(value) for value in project_ids})
    if not ids:
        return ["1 = 0"], []
    marker = "%s" if db_backend.connection_is_postgres(conn) else "?"
    markers = ", ".join(marker for _ in ids)
    clause = (
        "(EXISTS (SELECT 1 FROM deployment_run_items dri "
        "JOIN items i ON i.id=dri.item_id WHERE dri.run_id=dr.id "
        f"AND i.project_id IN ({markers})) OR "
        f"(dr.project_id IN ({markers}) AND NOT EXISTS "
        "(SELECT 1 FROM deployment_run_items dri WHERE dri.run_id=dr.id)))"
    )
    return [clause], [*ids, *ids]


def overview_run_selection(
    conn: Any,
    *,
    where: str,
    params: list[Any],
    priority_order: str,
    visible_project_ids: Collection[int] | None,
    limit: int,
) -> tuple[str, list[Any]]:
    """Union each authorized project's bounded window before hydrating runs."""
    visibility = ""
    selected_params = list(params)
    if visible_project_ids is not None:
        ids = sorted(visible_project_ids)
        marker = "%s" if db_backend.connection_is_postgres(conn) else "?"
        visibility = (" AND " if where else " WHERE ") + (
            "rp.project_id IN (" + ",".join(marker for _ in ids) + ")" if ids else "1=0"
        )
        selected_params.extend(ids)
    return (
        "SELECT DISTINCT ranked.id FROM (SELECT dr.id, ROW_NUMBER() OVER ("
        f"PARTITION BY rp.project_id ORDER BY {priority_order}"
        "dr.created_at DESC, dr.id DESC) AS ordinal FROM deployment_runs dr "
        "JOIN projects p ON p.id=dr.project_id "
        "JOIN deployment_flows df ON df.id=dr.flow "
        "JOIN (SELECT dri.run_id,i.project_id FROM deployment_run_items dri "
        "JOIN items i ON i.id=dri.item_id UNION "
        "SELECT own.id AS run_id,own.project_id FROM deployment_runs own "
        "WHERE NOT EXISTS (SELECT 1 FROM deployment_run_items m WHERE m.run_id=own.id)) rp "
        f"ON rp.run_id=dr.id {where}{visibility}"
        ") ranked WHERE ranked.ordinal<=%s",
        [*selected_params, limit],
    )


__all__ = ["run_project_scope"]
