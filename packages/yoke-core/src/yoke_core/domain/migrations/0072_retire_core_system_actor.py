"""Retire the core system actor; writes the engine makes itself carry no actor.

Older universes were seeded with a ``yoke-core`` system actor that held no
credential and only attributed engine-sent wake notices, their
cancellations, and a few grants and invites. This entry relaxes the two
references that required an actor, clears every reference to that row, and
deletes it. The row is found by its component, never by id: a universe born
after this entry has its first human at id 1, which is also why
``items.source`` loses its literal default of ``'2'`` — the human's id in
the older numbering. Every writer names its source actor; the column
defaults to the empty "no recorded source" token instead.
"""

from typing import Any

from yoke_core.domain.migration_serving_version import NEXT_RELEASE
from yoke_core.domain.schema_common import _table_exists

MINIMUM_SERVING_VERSION = NEXT_RELEASE

CORE_COMPONENT = "yoke-core"

#: ``items.source`` default as the catalog reports it.
ITEM_SOURCE_DEFAULT = "''::text"

#: References that an engine write may now leave empty.
RELAXED_COLUMNS = (
    ("session_messages", "sender_actor_id"),
    ("actor_invites", "invited_by_actor_id"),
)

#: Grants the retired actor held itself; they go with it.
ROLE_HOLDER_COLUMNS = (
    ("actor_org_roles", "actor_id"),
    ("actor_project_roles", "actor_id"),
)

_ACTOR_REFERENCES_SQL = """
SELECT cl.relname, att.attname, att.attnotnull
FROM pg_constraint con
JOIN pg_class cl ON cl.oid = con.conrelid
JOIN pg_namespace ns ON ns.oid = cl.relnamespace
JOIN pg_attribute att
  ON att.attrelid = con.conrelid AND att.attnum = ANY (con.conkey)
WHERE con.contype = 'f'
  AND con.confrelid = 'actors'::regclass
  AND ns.nspname = current_schema()
ORDER BY cl.relname, att.attname
"""


def _core_actor_id(conn: Any) -> int | None:
    row = conn.execute(
        "SELECT id FROM actors WHERE system_component = %s", (CORE_COMPONENT,)
    ).fetchone()
    return None if row is None else int(row[0])


def _actor_references(conn: Any) -> list[tuple[str, str, bool]]:
    return [
        (str(table), str(column), bool(not_null))
        for table, column, not_null in conn.execute(_ACTOR_REFERENCES_SQL)
    ]


def _count(conn: Any, table: str, column: str, actor_id: int) -> int:
    row = conn.execute(
        f"SELECT count(*) FROM {table} WHERE {column} = %s", (actor_id,)
    ).fetchone()
    return int(row[0])


def apply(conn: Any) -> None:
    if not _table_exists(conn, "actors"):
        return
    for table, column in RELAXED_COLUMNS:
        if _table_exists(conn, table):
            conn.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL")
    if _table_exists(conn, "items"):
        conn.execute("ALTER TABLE items ALTER COLUMN source SET DEFAULT ''")
    actor_id = _core_actor_id(conn)
    if actor_id is None:
        return
    references = _actor_references(conn)
    for table, column, not_null in references:
        if not not_null or (table, column) in ROLE_HOLDER_COLUMNS:
            continue
        count = _count(conn, table, column, actor_id)
        if count:
            raise RuntimeError(
                f"core_actor_reference_unexpected: {table}.{column} has {count} "
                f"rows naming the retired core actor (id {actor_id}). Recovery: "
                "retire or repair those rows through their registered command, "
                "then reboot the candidate so the converge reruns this entry."
            )
    for table, column, _not_null in references:
        if (table, column) in ROLE_HOLDER_COLUMNS:
            conn.execute(f"DELETE FROM {table} WHERE {column} = %s", (actor_id,))
        else:
            conn.execute(
                f"UPDATE {table} SET {column} = NULL WHERE {column} = %s",
                (actor_id,),
            )
    conn.execute("DELETE FROM actors WHERE id = %s", (actor_id,))


def invariants(conn: Any) -> None:
    if not _table_exists(conn, "actors"):
        return
    if _core_actor_id(conn) is not None:
        raise RuntimeError(
            "core_actor_present: the retired yoke-core system actor still "
            "exists. Recovery: boot the candidate so the converge applies "
            "0072_retire_core_system_actor before serving."
        )
    for table, column in RELAXED_COLUMNS:
        if not _table_exists(conn, table):
            continue
        row = conn.execute(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s "
            "AND column_name = %s",
            (table, column),
        ).fetchone()
        if row is not None and row[0] != "YES":
            raise RuntimeError(
                f"engine_reference_not_nullable: {table}.{column} still "
                "requires an actor. Recovery: boot the candidate so the "
                "converge applies 0072_retire_core_system_actor before serving."
            )
    row = conn.execute(
        "SELECT column_default FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = 'items' "
        "AND column_name = 'source'"
    ).fetchone()
    if row is not None and row[0] != ITEM_SOURCE_DEFAULT:
        raise RuntimeError(
            f"item_source_default_unconverged: items.source defaults to "
            f"{row[0]}. Recovery: boot the candidate so the converge applies "
            "0072_retire_core_system_actor before serving."
        )
