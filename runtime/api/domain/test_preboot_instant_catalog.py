"""Clock catalog reads refresh when schema initialization adds a declared table."""

from types import SimpleNamespace

import pytest

from yoke_core.domain import preboot_instant_parameters as catalog_state
from yoke_core.domain.preboot_instant_parameters import text_storage


def test_catalog_refreshes_a_previously_absent_clock(monkeypatch):
    monkeypatch.setattr(catalog_state, "_TYPES", {})
    catalog = [("items", "merged_at", "text")]
    reads = []

    class Connection:
        info = SimpleNamespace(host="test", port=1, dbname="initializing", user="test")

        def execute(self, sql, params):
            reads.append(sql)
            return SimpleNamespace(fetchall=lambda: list(catalog))

    conn = Connection()
    assert text_storage(conn, "items", "merged_at")
    catalog.append(("qa_runs", "started_at", "text"))
    assert text_storage(conn, "qa_runs", "started_at")
    assert len(reads) == 2
    assert text_storage(conn, "qa_runs", "started_at")
    assert len(reads) == 2


def test_missing_clock_still_refuses(monkeypatch):
    monkeypatch.setattr(catalog_state, "_TYPES", {})

    class Connection:
        info = SimpleNamespace(host="test", port=1, dbname="missing", user="test")

        def execute(self, sql, params):
            return SimpleNamespace(fetchall=lambda: [])

    with pytest.raises(ValueError, match="preboot_instant_storage_invalid"):
        text_storage(Connection(), "qa_runs", "started_at")
