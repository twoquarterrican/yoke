"""CLI/cmd tests: event_registry get/list/count read helpers."""

from __future__ import annotations

import pytest

from yoke_core.domain import events_crud
from runtime.api.events_crud_full_test_helpers import db_path as db_path
from runtime.api.fixtures.file_test_db import connect_test_db


def _seed_registry(
    db_path: str,
    name: str,
    *,
    kind: str = "lifecycle",
    event_type: str = "t",
    service: str = "cli",
    description: str = "d",
) -> None:
    conn = connect_test_db(db_path)
    try:
        conn.execute(
            "INSERT INTO event_registry "
            "(event_name, event_kind, event_type, owner_service, description) "
            "VALUES (%s, %s, %s, %s, %s)",
            (name, kind, event_type, service, description),
        )
        conn.commit()
    finally:
        conn.close()


class TestRegistryCmds:
    def test_get_returns_pipe_delimited_row(self, db_path):
        _seed_registry(
            db_path,
            "TestEvt",
            kind="lifecycle",
            event_type="test",
            service="cli",
            description="Test event",
        )
        result = events_crud.cmd_registry_get(db_path, "TestEvt")
        assert result == "TestEvt|lifecycle|test|cli|Test event|INFO"

    def test_get_not_found(self, db_path):
        with pytest.raises(LookupError, match="not found"):
            events_crud.cmd_registry_get(db_path, "Missing")

    def test_list(self, db_path):
        _seed_registry(db_path, "A", description="a")
        _seed_registry(db_path, "B", description="b")
        result = events_crud.cmd_registry_list(db_path)
        assert result.splitlines() == [
            "A|lifecycle|t|cli|a|INFO",
            "B|lifecycle|t|cli|b|INFO",
        ]

    def test_list_with_kind_and_service_filters(self, db_path):
        _seed_registry(db_path, "Life", kind="lifecycle", service="cli")
        _seed_registry(db_path, "Sys", kind="system", service="cli")
        _seed_registry(db_path, "SysApi", kind="system", service="api")

        by_kind = events_crud.cmd_registry_list(db_path, kind="system")
        assert "Life" not in by_kind
        assert "Sys|" in by_kind and "SysApi|" in by_kind

        by_both = events_crud.cmd_registry_list(db_path, kind="system", service="api")
        assert by_both.splitlines() == ["SysApi|system|t|api|d|INFO"]

    def test_count(self, db_path):
        assert events_crud.cmd_registry_count(db_path) == 0
        _seed_registry(db_path, "A")
        _seed_registry(db_path, "B")
        assert events_crud.cmd_registry_count(db_path) == 2
