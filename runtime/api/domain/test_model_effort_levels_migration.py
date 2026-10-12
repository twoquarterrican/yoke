"""Stored native-selector Levels converge without preserving the fallback path."""

import importlib
from yoke_contracts.levels import levels_payload, default_levels

migration = importlib.import_module(
    "yoke_core.domain.migrations.0071_model_effort_levels"
)


def test_legacy_variants_fold_and_fallback_is_retired():
    old = [
        {
            "name": "JUNIOR",
            "glyph": "🐥",
            "options": [
                {
                    "surface": "cursor-cli",
                    "model": "grok-4.7-high",
                    "reasoning_effort": "high",
                    "context_window_tokens": None,
                    "fallback": {
                        "surface": "cursor-cli",
                        "model": "claude-opus-5-5-medium",
                        "reasoning_effort": "medium",
                    },
                },
                {
                    "surface": "cursor-cli",
                    "model": "grok-4.7-high-fast",
                    "reasoning_effort": "high",
                    "context_window_tokens": None,
                },
            ],
        }
    ]
    assert migration.converged(old) == [
        {
            "name": "JUNIOR",
            "glyph": "🐥",
            "options": [{"model": "grok-4.7", "min_effort": "high"}],
        }
    ]


def test_current_document_is_idempotent():
    current = levels_payload(default_levels())
    assert migration.converged(current) == current
    assert migration.converged(migration.converged(current)) == current


def test_duplicate_native_surface_rows_keep_the_lower_threshold():
    old = [
        {
            "name": "SENIOR",
            "glyph": "🦉",
            "options": [
                {
                    "surface": "claude-cli",
                    "model": "claude-opus-5-5",
                    "reasoning_effort": "high",
                },
                {
                    "surface": "cursor-cli",
                    "model": "claude-opus-5-5-medium",
                    "reasoning_effort": "medium",
                },
            ],
        }
    ]
    assert migration.converged(old)[0]["options"] == [
        {"model": "claude-opus-5-5", "min_effort": "medium"}
    ]


def test_apply_preserves_custom_levels_and_marks_only_item_or_level_launches():
    import json
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE universe_settings (key TEXT PRIMARY KEY,value TEXT,updated_at TEXT,updated_by_actor_id INTEGER);
        CREATE TABLE project_capabilities (id INTEGER PRIMARY KEY,type TEXT,settings TEXT);
        CREATE TABLE projects (id INTEGER PRIMARY KEY,public_item_prefix TEXT);
        CREATE TABLE items (id INTEGER PRIMARY KEY,project_id INTEGER,project_sequence INTEGER);
        CREATE TABLE session_launches (launch_id TEXT PRIMARY KEY,project_id INTEGER,session_name TEXT,requested_level TEXT,level_placement TEXT);
        INSERT INTO projects VALUES (1,'EXAMPLE');
        INSERT INTO items VALUES (42,1,7);
        INSERT INTO session_launches VALUES ('item',1,'EXAMPLE-7: A title',NULL,NULL);
        INSERT INTO session_launches VALUES ('steering',1,'Universe steering',NULL,NULL);
        INSERT INTO session_launches VALUES ('level',1,NULL,'SENIOR','{"chosen":{"model":"gpt-6.1-sol"}}');
    """)
    current = levels_payload(default_levels())
    conn.execute(
        "INSERT INTO universe_settings VALUES ('levels',?,'now',NULL)",
        (json.dumps(current),),
    )
    conn.execute(
        "INSERT INTO project_capabilities VALUES (1,'session-routing',?)",
        (json.dumps({"levels": current}),),
    )
    migration.apply(conn)
    migration.invariants(conn)
    assert (
        json.loads(
            conn.execute(
                "SELECT value FROM universe_settings WHERE key='levels'"
            ).fetchone()[0]
        )
        == current
    )
    assert json.loads(
        conn.execute(
            "SELECT value FROM universe_settings WHERE key='cursor_quota_order'"
        ).fetchone()[0]
    ) == ["Cursor Models", "Other Models"]
    rows = dict(
        conn.execute(
            "SELECT launch_id,level_placement FROM session_launches"
        ).fetchall()
    )
    assert json.loads(rows["item"]) == {"work_required": True}
    assert json.loads(rows["level"]) == {
        "chosen": {"model": "gpt-6.1-sol"},
        "work_required": True,
    }
    assert rows["steering"] is None
    migration.apply(conn)
    migration.invariants(conn)
