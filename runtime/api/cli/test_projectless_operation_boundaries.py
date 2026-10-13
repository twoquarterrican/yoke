"""Projectless commands preserve scope and machine-owned output."""

import pytest

from yoke_cli.commands.adapters import doctor
from yoke_cli.config import status_doctor, universe_export_download
from yoke_cli.project_install import runner
from yoke_cli.project_install.files import ProjectInstallError
from yoke_contracts.project_defaults import MissingProjectError
from yoke_core.domain import machine_config_status
from yoke_core.domain.universe_export_destination import resolve_export_destination


def test_install_refuses_non_git_before_bundle_or_config(tmp_path, monkeypatch):
    monkeypatch.setattr(
        runner, "_resolve_bundle", lambda *_a, **_k: pytest.fail("bundle read")
    )
    with pytest.raises(ProjectInstallError, match="project_git_required.*git init"):
        runner.install(tmp_path, project_id=7, force=True, commit=False)
    assert list(tmp_path.iterdir()) == []


def test_doctor_last_run_refuses_before_dispatch(monkeypatch, capsys):
    def refuse(_project):
        raise MissingProjectError(
            "project_required: pass --project P. Accessible projects: mine."
        )

    monkeypatch.setattr(doctor, "required_project_context", refuse)
    monkeypatch.setattr(
        doctor, "dispatch_and_emit", lambda **_k: pytest.fail("unscoped read")
    )
    assert doctor.doctor_last_run_get([]) == 2
    assert "Accessible projects: mine" in capsys.readouterr().err


def test_status_without_project_never_reads_a_foreign_doctor_receipt(monkeypatch):
    monkeypatch.setattr(
        "yoke_cli.transport.dispatcher.call_dispatcher",
        lambda **_k: pytest.fail("unscoped doctor receipt"),
    )
    report = status_doctor.attach_doctor({"server": {"reachable": True}})
    assert report["doctor"]["summary"].startswith("health unverified")


def test_export_defaults_stay_outside_cwd(tmp_path, monkeypatch):
    home = tmp_path / "machine-home"
    cwd = tmp_path / "projectless"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("YOKE_MACHINE_HOME", str(home))
    local = resolve_export_destination(None, "demo")
    https = universe_export_download._destination(None, "demo.tar")
    assert local.parent == https.parent == home / "exports"
    assert list(cwd.iterdir()) == []
    assert resolve_export_destination(str(cwd) + "/", "demo").parent == cwd


def test_project_mapping_is_the_same_warning_in_cli_and_core(tmp_path, monkeypatch):
    from yoke_cli.config import status

    config = tmp_path / "config.json"
    config.write_text("{}")
    for module in (status, machine_config_status):
        report = module._project_status(tmp_path, config)
        (issue,) = report["issues"]
        assert issue["code"] == "project_mapping_missing"
        assert issue["severity"] == "warning"
        assert "yoke project register" in issue["hint"]
