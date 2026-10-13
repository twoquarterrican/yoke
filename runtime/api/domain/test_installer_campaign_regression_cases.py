"""Recovery recipes use executable method contracts and fail closed."""

from io import BytesIO
from subprocess import CompletedProcess
import shutil
import subprocess
import sys
from types import SimpleNamespace
from urllib import request

import pytest

from yoke_contracts.codex_config_posture import plan
from yoke_core.domain.installer_campaign_regression_cases import (
    INSTALLER_RECOVERY_CASES,
    _LATE_HARNESS_SCRIPT,
    _STALE_RELEASE_SCRIPT,
)
from yoke_core.domain.machine_qa_method_contracts import validate_machine_method_config
from yoke_core.domain.installer_campaign_execution_target import installer_campaign_cases_for_target
from yoke_core.domain.ssh_mac_host_control import SshMacHostControl
from yoke_core.domain.ssh_linux_host_control import SshLinuxHostControl
from runtime.api.domain.test_qa_release_channel_target import _target


def test_every_recovery_recipe_satisfies_its_method_contract():
    for case in INSTALLER_RECOVERY_CASES:
        validate_machine_method_config(
            case["method_id"],
            case["method_config"],
            entry_surface=case["entry_surface"],
            required_completion=case["required_completion"],
        )


def test_projected_recovery_entries_expand_through_both_real_host_adapters():
    control = SimpleNamespace(path_state=SimpleNamespace(yoke_bin="/tmp/fixture/bin/yoke"))
    cases = installer_campaign_cases_for_target(
        _target("prod"), primary_machine="primary-test", joining_machine="joining-test",
    )
    for case in cases:
        if case["entry_surface"]:
            mac = SshMacHostControl._resolve_entry_surface(control, case["entry_surface"])
            linux = SshLinuxHostControl._entry_surface(control, case["entry_surface"])
            assert mac == linux
            assert "{yoke_bin}" not in mac


def test_stale_lookup_selects_the_highest_published_predecessor(monkeypatch, capsys):
    def open_response(url, **kwargs):
        if url.endswith(".json"):
            return BytesIO(b'{"version":"2.0.0","index_url":"https://example.invalid/simple"}')
        return BytesIO(
            b'<a href="yoke_cli-1.0-py3-none-any.whl">older</a>'
            b'<a href="yoke_cli-1.5-py3-none-any.whl">previous</a>'
            b'<a href="yoke_cli-2.1-py3-none-any.whl">newer</a>'
        )
    monkeypatch.setattr(request, "urlopen", open_response)
    monkeypatch.setattr(sys, "argv", ["fixture", "https://example.invalid", "stable"])
    exec(compile(_STALE_RELEASE_SCRIPT, "stale_fixture", "exec"), {})
    assert capsys.readouterr().out.strip() == "2.0.0 1.5"


def test_stale_lookup_network_failure_teaches_recovery(monkeypatch):
    def refuse(*args, **kwargs):
        raise OSError("unavailable")
    monkeypatch.setattr(request, "urlopen", refuse)
    monkeypatch.setattr(sys, "argv", ["fixture", "https://example.invalid", "stable"])
    with pytest.raises(SystemExit, match="stale_release_lookup_failed"):
        exec(compile(_STALE_RELEASE_SCRIPT, "stale_fixture", "exec"), {})


def _late_fixture(monkeypatch, tmp_path, setup_returncode):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))
    executable = tmp_path / "codex"
    executable.write_text("fixture binary")
    monkeypatch.setattr(shutil, "which", lambda name: str(executable))
    monkeypatch.setattr(sys, "argv", ["fixture", "setup-fixture"])
    monkeypatch.setattr(
        subprocess, "run",
        lambda argv, **kwargs: CompletedProcess(argv, setup_returncode if kwargs.get("shell") else 0),
    )
    return executable


def test_failed_setup_restores_the_preserved_harness(monkeypatch, tmp_path):
    executable = _late_fixture(monkeypatch, tmp_path, 1)
    with pytest.raises(SystemExit, match="late_harness_setup_failed"):
        exec(compile(_LATE_HARNESS_SCRIPT, "late_fixture", "exec"), {})
    assert executable.read_text() == "fixture binary"
    assert not executable.with_name("codex.installer-qa-saved").exists()


def test_configured_permissions_without_trusted_hooks_do_not_pass(monkeypatch, tmp_path):
    executable = _late_fixture(monkeypatch, tmp_path, 0)
    config = tmp_path / ".codex/config.toml"
    config.parent.mkdir()
    config.write_text(plan("")[0])
    with pytest.raises(SystemExit, match="late_harness_hooks_unready"):
        exec(compile(_LATE_HARNESS_SCRIPT, "late_fixture", "exec"), {})
    assert executable.exists()
