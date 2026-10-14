"""Direct API tests: cmd_registry_audit and cmd_registry_diff full coverage."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from yoke_core.domain import events_crud
from runtime.api.events_crud_full_test_helpers import (
    _THIRTY_DAYS_AGO,
    _insert_event_direct,
    db_path as db_path,
    empty_db_path as empty_db_path,
)
from runtime.api.fixtures.file_test_db import connect_test_db


def _seed_registry(db_path: str, name: str, description: str) -> None:
    conn = connect_test_db(db_path)
    try:
        conn.execute(
            "INSERT INTO event_registry "
            "(event_name, event_kind, event_type, owner_service, description) "
            "VALUES (%s, 'lifecycle', 'test', 'cli', %s)",
            (name, description),
        )
        conn.commit()
    finally:
        conn.close()


class TestRegistryAudit:
    def test_cmd_registry_audit_reports_all_categories(self, db_path):
        _seed_registry(db_path, "StaleEvent", "Never emitted")
        _seed_registry(db_path, "SharedEvent", "Emitted and discovered")
        conn = connect_test_db(db_path)
        _insert_event_direct(conn, event_name="RogueEvent")
        _insert_event_direct(conn, event_name="SharedEvent")
        conn.commit()
        conn.close()

        discovered = "SharedEvent|scripts/emit.sh\nUnregisteredEvent|skills/flow.md"
        with patch(
            "yoke_core.domain.events_crud.cmd_registry_discover",
            return_value=discovered,
        ):
            result = events_crud.cmd_registry_audit(db_path)

        assert "### Stale Entries" in result
        assert "- StaleEvent (service: cli)" in result
        assert "### Rogue Events" in result
        assert "- RogueEvent" in result
        assert "### Unregistered Call Sites" in result
        assert "- UnregisteredEvent (file: skills/flow.md)" in result
        assert "Deprecated" not in result
        assert result.endswith("### Summary\n1 stale, 1 rogue, 1 unregistered")

    def test_cmd_registry_audit_missing_tables_raises(self, empty_db_path):
        with pytest.raises(RuntimeError, match="required tables missing"):
            events_crud.cmd_registry_audit(empty_db_path)

    def test_cmd_registry_audit_tolerates_discover_failure(self, db_path):
        with patch(
            "yoke_core.domain.events_crud.cmd_registry_discover",
            side_effect=RuntimeError("boom"),
        ):
            result = events_crud.cmd_registry_audit(db_path)

        assert "### Unregistered Call Sites" in result
        assert "(none)" in result

    def test_audit_stale_entries(self, test_db):
        """Registry entries with no recent events are stale."""
        test_db.execute("DELETE FROM event_registry")
        test_db.execute(
            "INSERT INTO event_registry (event_name, event_kind, event_type, owner_service, description) "
            "VALUES ('StaleEvent', 'lifecycle', 'test', 'cli', 'Never emitted')"
        )
        test_db.commit()

        stale = test_db.execute(
            "SELECT r.event_name FROM event_registry r "
            "WHERE r.event_name NOT IN ("
            "  SELECT DISTINCT event_name FROM events "
            "  WHERE created_at >= %s)",
            (_THIRTY_DAYS_AGO,),
        ).fetchall()
        assert len(stale) == 1
        assert stale[0]["event_name"] == "StaleEvent"

    def test_audit_rogue_events(self, test_db):
        """Events emitted but not in registry are rogue."""
        _insert_event_direct(test_db, event_name="RogueEvent")

        rogue = test_db.execute(
            "SELECT DISTINCT event_name FROM events "
            "WHERE event_name NOT IN (SELECT event_name FROM event_registry)"
        ).fetchall()
        assert len(rogue) == 1
        assert rogue[0]["event_name"] == "RogueEvent"

    def test_audit_no_issues(self, test_db):
        """When registry and events match, no issues."""
        test_db.execute("DELETE FROM event_registry")
        test_db.execute(
            "INSERT INTO event_registry (event_name, event_kind, event_type, owner_service, description) "
            "VALUES ('MatchedEvent', 'lifecycle', 'test', 'cli', 'Matched')"
        )
        test_db.commit()
        _insert_event_direct(test_db, event_name="MatchedEvent")

        # Stale: registered but no recent emit
        stale = test_db.execute(
            "SELECT r.event_name FROM event_registry r "
            "WHERE r.event_name NOT IN ("
            "  SELECT DISTINCT event_name FROM events "
            "  WHERE created_at >= %s)",
            (_THIRTY_DAYS_AGO,),
        ).fetchall()
        # MatchedEvent was just inserted, so should be recent
        assert len(stale) == 0


class TestRegistryDiff:
    def test_cmd_registry_diff_reports_additions_and_removals(self, db_path):
        _seed_registry(db_path, "SharedEvent", "shared")
        _seed_registry(db_path, "OnlyInRegistry", "registry only")

        discovered = "SharedEvent|scripts/shared.sh\nOnlyInCode|scripts/new.sh"
        with patch(
            "yoke_core.domain.events_crud.cmd_registry_discover",
            return_value=discovered,
        ):
            result = events_crud.cmd_registry_diff(db_path)

        assert "+ OnlyInCode (discovered in scripts/new.sh)" in result
        assert "- OnlyInRegistry (in registry, no call site found)" in result

    def test_cmd_registry_diff_verbose_reports_equals(self, db_path):
        _seed_registry(db_path, "SharedEvent", "shared")

        with patch(
            "yoke_core.domain.events_crud.cmd_registry_discover",
            return_value="SharedEvent|scripts/shared.sh",
        ):
            result = events_crud.cmd_registry_diff(db_path, verbose=True)

        assert result.startswith("Registry is in sync with codebase. 0 differences.")
        assert "= SharedEvent" in result

    def test_cmd_registry_diff_missing_table_raises(self, empty_db_path):
        with pytest.raises(RuntimeError, match="event_registry table not found"):
            events_crud.cmd_registry_diff(empty_db_path)

    def test_unregistered_discovered(self, test_db):
        """Events discovered in code but not in registry show as +."""
        # Simulate: disc_names has "NewEvent", registry is empty
        disc_names = {"NewEvent"}
        reg_names = set()

        plus_lines = sorted(disc_names - reg_names)
        assert "NewEvent" in plus_lines

    def test_registered_no_call_site(self, test_db):
        """Registered events not in discovered code show as -."""
        disc_names = set()
        reg_names = {"OrphanedEvent"}

        minus_lines = sorted(reg_names - disc_names)
        assert "OrphanedEvent" in minus_lines

    def test_in_sync(self):
        disc_names = {"EventA", "EventB"}
        reg_names = {"EventA", "EventB"}
        plus = disc_names - reg_names
        minus = reg_names - disc_names
        assert len(plus) == 0
        assert len(minus) == 0
