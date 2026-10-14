"""Boot projects the code event catalog into ``event_registry`` exactly."""

from __future__ import annotations

from yoke_core.domain import events_crud
from yoke_core.domain.event_catalog import EVENT_CATALOG, EventSpec
from yoke_core.domain.event_registry_converge import converge_event_registry
from yoke_core.domain.events import emit_event
from yoke_core.domain.events_select import VALID_SEVERITIES
from yoke_core.domain.migration_restore_point import RESTORE_POINT_ENV
from yoke_core.domain.schema_init import converge_core_schema

_REGISTRY_SQL = (
    "SELECT event_name, event_kind, event_type, owner_service, "
    "severity_default, description FROM event_registry"
)


def _registry(conn) -> dict[str, EventSpec]:
    return {row[0]: EventSpec(*row) for row in conn.execute(_REGISTRY_SQL).fetchall()}


def test_boot_converge_leaves_exactly_the_code_catalog(test_db, monkeypatch) -> None:
    monkeypatch.setenv(RESTORE_POINT_ENV, "event-registry-converge-test-snapshot")
    converge_core_schema(test_db)
    drifted = next(iter(EVENT_CATALOG))
    test_db.execute(
        "INSERT INTO event_registry (event_name, event_kind, event_type, "
        "owner_service, description) VALUES "
        "('SkipHopPerformed', 'workflow', 'skip_hop', 'cli', 'No producer'), "
        "('AutoJoinDomainChanged', 'audit', 'org', 'api', 'No producer')"
    )
    test_db.execute(
        "UPDATE event_registry SET description = 'stale', severity_default = 'DEBUG' "
        "WHERE event_name = %s",
        (drifted,),
    )
    test_db.execute("DELETE FROM event_registry WHERE event_name = 'ItemStatusChanged'")
    test_db.commit()

    converge_core_schema(test_db)

    assert _registry(test_db) == dict(EVENT_CATALOG)


def test_converge_rerun_writes_nothing(test_db, monkeypatch) -> None:
    monkeypatch.setenv(RESTORE_POINT_ENV, "event-registry-converge-test-snapshot")
    converge_core_schema(test_db)

    again = converge_event_registry(test_db)

    assert again.written == ()
    assert again.deleted == ()


def test_converge_reports_what_it_wrote_and_deleted(test_db, monkeypatch) -> None:
    monkeypatch.setenv(RESTORE_POINT_ENV, "event-registry-converge-test-snapshot")
    converge_core_schema(test_db)
    test_db.execute("DELETE FROM event_registry WHERE event_name = 'ItemStatusChanged'")
    test_db.execute(
        "INSERT INTO event_registry (event_name, event_kind, event_type, "
        "owner_service, description) VALUES "
        "('PathClaimSnapshotRefreshed', 'lifecycle', 'path_claim', 'cli', 'gone')"
    )

    result = converge_event_registry(test_db)

    assert result.written == ("ItemStatusChanged",)
    assert result.deleted == ("PathClaimSnapshotRefreshed",)


def test_unregistered_emission_lands_and_is_reported_rogue(
    test_db, monkeypatch
) -> None:
    monkeypatch.setenv(RESTORE_POINT_ENV, "event-registry-converge-test-snapshot")
    converge_core_schema(test_db)
    assert "UncataloguedProbeEmitted" not in EVENT_CATALOG

    emit_event(
        "UncataloguedProbeEmitted",
        event_kind="system",
        event_type="registry_probe",
        conn=test_db,
        transactional=True,
    )
    test_db.commit()
    monkeypatch.setattr(events_crud, "cmd_registry_discover", lambda *_a, **_k: "")

    report = events_crud.cmd_registry_audit()
    rogue = report.split("### Rogue Events (emitted, not registered)")[1]
    rogue = rogue.split("###")[0]
    assert "- UncataloguedProbeEmitted" in rogue


def test_catalog_rows_are_complete() -> None:
    for spec in EVENT_CATALOG.values():
        assert spec.severity in VALID_SEVERITIES, spec
        assert all(spec), spec
