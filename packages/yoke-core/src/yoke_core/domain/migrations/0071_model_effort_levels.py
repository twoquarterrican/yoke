"""Converge stored launch-selector Levels to model/minimum-effort rows."""

from yoke_contracts.levels import parse_levels, levels_payload
from yoke_contracts.model_level_resolution import effort_ordinal, normalized_effort
from yoke_contracts.model_reference import lookup_stem
from yoke_contracts.timestamps import utc_now
from yoke_core.domain import db_backend, json_helper
from yoke_core.domain.db_helpers import instant_parameter
from yoke_core.domain.migration_serving_version import NEXT_RELEASE
from yoke_core.domain.schema_common import _table_exists

MINIMUM_SERVING_VERSION = NEXT_RELEASE


def converged(raw):
    """Fold duplicate native variants and retire exhausted-pool fallbacks."""
    result = []
    for level in raw:
        entries = {}
        for option in level["options"]:
            if "min_effort" in option:
                model, effort = option["model"], option["min_effort"]
            else:
                model = lookup_stem(option["model"]).removeprefix("cursor-")
                effort = normalized_effort(option["reasoning_effort"])
            existing = entries.get(model)
            if existing is None or effort_ordinal(effort) < effort_ordinal(existing):
                entries[model] = effort
        result.append(
            {
                "name": level["name"],
                "glyph": level["glyph"],
                "options": [
                    {"model": model, "min_effort": effort}
                    for model, effort in entries.items()
                ],
            }
        )
    return levels_payload(parse_levels(result))


def _documents(conn):
    p = "%s" if db_backend.connection_is_postgres(conn) else "?"
    if _table_exists(conn, "universe_settings"):
        for row in conn.execute(
            f"SELECT key,value FROM universe_settings WHERE key={p}", ("levels",)
        ).fetchall():
            yield "universe_settings", "key", row[0], row[1]
    if _table_exists(conn, "project_capabilities"):
        for row in conn.execute(
            f"SELECT id,settings FROM project_capabilities WHERE type={p}",
            ("session-routing",),
        ).fetchall():
            yield "project_capabilities", "id", row[0], row[1]


def _decode(table, key, raw):
    try:
        document = json_helper.loads_text(str(raw))
        levels = document if table == "universe_settings" else document["levels"]
        converted = converged(levels)
        return converted if table == "universe_settings" else {"levels": converted}
    except (TypeError, ValueError, KeyError) as exc:
        raise RuntimeError(
            f"levels_convergence_invalid: {table} row {key} cannot converge: {exc}. "
            "Recovery: repair the serving universe Levels or project session-routing "
            "document with strictly increasing efforts per model, then retry rehearsal or boot."
        ) from exc


def apply(conn):
    p = "%s" if db_backend.connection_is_postgres(conn) else "?"
    for table, key_column, key, raw in _documents(conn):
        updated = json_helper.dumps_compact(_decode(table, key, raw))
        value_column = "value" if table == "universe_settings" else "settings"
        conn.execute(
            f"UPDATE {table} SET {value_column}={p} WHERE {key_column}={p}",
            (updated, key),
        )
    if _table_exists(conn, "universe_settings"):
        conn.execute(
            "INSERT INTO universe_settings (key,value,updated_at,updated_by_actor_id) "
            f"VALUES ({p},{p},{p},NULL) ON CONFLICT (key) DO NOTHING",
            (
                "cursor_quota_order",
                json_helper.dumps_compact(["Cursor Models", "Other Models"]),
                instant_parameter(conn, utc_now()),
            ),
        )


def invariants(conn):
    for table, _, key, raw in _documents(conn):
        original = json_helper.loads_text(str(raw))
        assert original == _decode(table, key, raw), (
            f"{table} row {key} has unconverged levels"
        )
    if _table_exists(conn, "universe_settings"):
        p = "%s" if db_backend.connection_is_postgres(conn) else "?"
        row = conn.execute(
            f"SELECT value FROM universe_settings WHERE key={p}",
            ("cursor_quota_order",),
        ).fetchone()
        ordered = json_helper.loads_text(str(row[0]))
        assert len(ordered) == 2 and set(ordered) == {
            "Cursor Models",
            "Other Models",
        }, "Cursor quota order must contain its two monthly pools exactly once"
