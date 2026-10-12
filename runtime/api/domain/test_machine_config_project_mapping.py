"""One machine-local checkout per project across every connection."""

import pytest
from yoke_contracts.machine_config import schema as contract
from yoke_contracts.machine_config import runtime
from yoke_cli.config import machine_config
from yoke_core.domain.project_checkout_locations import checkout_for_project_id


@pytest.mark.parametrize("env", ["prod", "prod-db-admin", "stage", "local", "other"])
def test_all_readers_share_one_entry(tmp_path, monkeypatch, env):
    import json

    repo = tmp_path / "repo"
    repo.mkdir()
    config = tmp_path / "config.json"
    payload = {
        "projects": [{"checkout": str(repo), "project_id": 7}],
        "active_env": "prod",
    }
    config.write_text(json.dumps(payload))
    monkeypatch.setenv("YOKE_ENV", env)
    assert contract.project_entry_for_checkout(payload, repo) == {"project_id": 7}
    assert contract.mapped_checkouts(payload) == [(str(repo), 7)]
    assert runtime.project_id(repo, config) == 7
    assert runtime.installed_project_ids(config) == {7}
    assert machine_config.configured_projects(config)[0].project_id == 7
    assert checkout_for_project_id(7, config_path=config) == repo


def test_upsert_replaces_project_checkout_and_preserves_other_projects():
    projects = [
        {"checkout": "/co/a", "project_id": 1},
        {"checkout": "/co/b", "project_id": 2},
    ]
    assert (
        contract.existing_checkout_for_slot(projects, checkout="/co/new", project_id=1)
        == "/co/a"
    )
    assert contract.upsert_project_entry(
        projects, checkout="/co/new", project_id=1
    ) == [
        {"checkout": "/co/b", "project_id": 2},
        {"checkout": "/co/new", "project_id": 1},
    ]


def test_duplicate_project_refuses_with_recovery():
    projects = [
        {"checkout": "/co/a", "project_id": 1},
        {"checkout": "/co/b", "project_id": 1},
    ]
    with pytest.raises(
        contract.MachineConfigContractError,
        match="project_id_duplicate.*repair projects",
    ):
        contract.normalize_projects(projects)
