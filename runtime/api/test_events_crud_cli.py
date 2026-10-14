"""CLI argument-parsing and exit-code tests for yoke_core.domain.events_crud."""

from __future__ import annotations

import os
import subprocess
import sys
from unittest.mock import patch

import pytest

from yoke_core.domain import events_crud as ec
from runtime.api.events_crud_test_fixtures import (  # noqa: F401
    _insert_event,
    db_path as db_path,
)
from runtime.api.fixtures.file_test_db import connect_test_db
from runtime.api.fixtures.pg_testdb import test_database as pg_test_database


class TestCLI:
    def test_module_entrypoint_initializes_without_double_import(
        self, tmp_path
    ) -> None:
        with pg_test_database():
            env = os.environ.copy()
            env.pop("YOKE_DB", None)
            result = subprocess.run(
                [sys.executable, "-m", "yoke_core.domain.events_crud", "init"],
                capture_output=True,
                env=env,
                text=True,
            )
        assert result.returncode == 0, result.stderr

    def test_no_args_exit_2(self) -> None:
        """Exit code 2 for usage errors."""
        assert ec.main([]) == 2

    def test_unknown_subcmd_exit_2(self) -> None:
        assert ec.main(["nonexistent"]) == 2

    def test_init_exit_0(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        assert ec.main(["init"]) == 0

    def test_registry_get_not_found_exit_1(self, db_path: str, monkeypatch) -> None:
        """Exit code 1 for not-found."""
        monkeypatch.setenv("YOKE_DB", db_path)
        assert ec.main(["registry", "get", "NonExistent"]) == 1

    def test_insert_missing_required_exit_2(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        assert ec.main(["insert", "--event-id", "x"]) == 2

    def test_full_insert_exit_0(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        rc = ec.main(
            [
                "insert",
                "--event-id",
                "cli-evt-1",
                "--source-type",
                "agent",
                "--session-id",
                "s1",
                "--event-kind",
                "system",
                "--event-type",
                "tool_call",
                "--event-name",
                "HarnessToolCallCompleted",
                "--skip-severity",
            ]
        )
        assert rc == 0

    def test_list_with_limit(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        for i in range(10):
            _insert_event(db_path, event_id=f"lim-{i}")
        assert ec.main(["list", "--limit", "5"]) == 0

    def test_tail_cli(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        _insert_event(db_path, event_id="tail-cli-1")
        assert ec.main(["tail", "5"]) == 0
        assert ec.main(["tail", "--limit", "5"]) == 0

    def test_severity_config_cli(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        assert ec.main(["severity-config", "set", "*", "*", "WARN"]) == 0
        assert ec.main(["severity-config", "list"]) == 0

    def test_severity_check_cli(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        assert ec.main(["severity-check", "Any", "agent", "INFO"]) == 0

    def test_registry_get_cli_prints_row(
        self, db_path: str, monkeypatch, capsys
    ) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        conn = connect_test_db(db_path)
        try:
            conn.execute(
                "INSERT INTO event_registry "
                "(event_name, event_kind, event_type, owner_service, description) "
                "VALUES ('CliSeenEvent', 'system', 'test', 'cli', 'Seeded row')"
            )
            conn.commit()
        finally:
            conn.close()
        assert ec.main(["registry", "get", "CliSeenEvent"]) == 0
        assert capsys.readouterr().out.strip() == (
            "CliSeenEvent|system|test|cli|Seeded row|INFO"
        )

    def test_registry_get_without_name_exit_2(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        assert ec.main(["registry", "get"]) == 2

    def test_registry_list_cli(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        assert ec.main(["registry", "list"]) == 0

    def test_registry_list_cli_passes_filters(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        with patch(
            "yoke_core.domain.events_crud.cmd_registry_list", return_value=""
        ) as listing:
            assert (
                ec.main(["registry", "list", "--kind", "system", "--service", "cli"])
                == 0
            )
        listing.assert_called_once_with(db_path, kind="system", service="cli")

    def test_registry_list_unknown_argument_exit_2(
        self, db_path: str, monkeypatch
    ) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        assert ec.main(["registry", "list", "--status", "active"]) == 2

    def test_registry_count_cli(self, db_path: str, monkeypatch, capsys) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        assert ec.main(["registry", "count"]) == 0
        assert capsys.readouterr().out.strip() == "0"

    def test_insert_cli_parses_numeric_fields(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        rc = ec.main(
            [
                "insert",
                "--event-id",
                "cli-num-1",
                "--source-type",
                "agent",
                "--session-id",
                "s1",
                "--event-kind",
                "system",
                "--event-type",
                "tool_call",
                "--event-name",
                "HarnessToolCallCompleted",
                "--duration-ms",
                "150",
                "--exit-code",
                "0",
                "--task-num",
                "7",
                "--skip-severity",
            ]
        )
        assert rc == 0

    def test_insert_unknown_flag_exit_2(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        assert ec.main(["insert", "--bogus", "x"]) == 2

    def test_registry_cli_requires_subcommand(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        assert ec.main(["registry"]) == 2

    @pytest.mark.parametrize("writer", ["add", "update", "deprecate", "delete"])
    def test_registry_has_no_writer_subcommands(
        self, writer: str, db_path: str, monkeypatch
    ) -> None:
        """Registry rows come from the code catalog, so the CLI only reads."""
        monkeypatch.setenv("YOKE_DB", db_path)
        assert ec.main(["registry", writer, "AnyEvent"]) == 2

    def test_registry_discover_cli(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        with patch(
            "yoke_core.domain.events_crud.cmd_registry_discover",
            return_value="Evt|scripts/e.sh",
        ) as discover:
            assert ec.main(["registry", "discover"]) == 0
        discover.assert_called_once_with()

    def test_registry_audit_cli(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        with patch(
            "yoke_core.domain.events_crud.cmd_registry_audit", return_value="audit ok"
        ) as audit:
            assert ec.main(["registry", "audit"]) == 0
        audit.assert_called_once_with(db_path)

    def test_registry_diff_cli_verbose(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        with patch(
            "yoke_core.domain.events_crud.cmd_registry_diff", return_value="diff ok"
        ) as diff:
            assert ec.main(["registry", "diff", "--verbose"]) == 0
        diff.assert_called_once_with(db_path, verbose=True)

    def test_registry_unknown_subcommand_exit_2(
        self, db_path: str, monkeypatch
    ) -> None:
        monkeypatch.setenv("YOKE_DB", db_path)
        assert ec.main(["registry", "wat"]) == 2
