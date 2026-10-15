"""Commit-clock releases keep ordering, relay origin and exact product bytes."""

import subprocess
from types import SimpleNamespace
import zipfile

import pytest

from yoke_contracts.engine_version import compare_engine_versions
from yoke_core.tools.session_relay_release import (
    RelayReleaseError,
    release_version_from_build,
)
from yoke_core.tools import local_wheel_constraints, session_relay_release_install


def test_commit_minutes_order_numerically():
    assert compare_engine_versions("0.2.0.202610140941", "0.2.0.202610140942") == -1
    assert compare_engine_versions("0.2.0.202610140941", "0.2.0.202610140941") == 0
    assert compare_engine_versions("0.2.0.202610150941", "0.2.0.202610140942") == 1


def test_relay_keeps_exact_canonical_handshake_version():
    assert release_version_from_build("0.2.0.202610140941") == "0.2.0.202610140941"


@pytest.mark.parametrize("value", ["0.2.0", "v0.2.0.202610140941", "0.2.0+other"])
def test_relay_refuses_noncanonical_build_with_recovery(value):
    with pytest.raises(RelayReleaseError, match="publish matching wheels"):
        release_version_from_build(value)


def test_container_constraints_bind_actual_wheel_paths(tmp_path):
    wheel = tmp_path / "yoke_core-0.2.0.202610140941-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as out:
        out.writestr(
            "yoke_core.dist-info/METADATA",
            "Name: yoke-core\nVersion: 0.2.0.202610140941\n",
        )
    assert local_wheel_constraints.constraints_for_wheelhouse(
        tmp_path, ["yoke-core"]
    ) == [f"yoke-core @ {wheel.as_uri()}"]


def test_relay_install_binds_every_product_to_declared_origin(tmp_path):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, "", "injected download refusal")

    with pytest.raises(RelayReleaseError, match="injected download refusal"):
        session_relay_release_install._install_candidate(
            SimpleNamespace(state_dir=tmp_path),
            release="0.2.0.202610140941",
            served_build="0.2.0.202610140941",
            index="https://packages.example.com/simple/",
            runtime_python=tmp_path / "runtime-python",
            create_venv=lambda path: path.mkdir(),
            runner=run,
        )
    products = [arg for arg in calls[0] if arg.startswith("https://")]
    assert set(products) == {
        "https://packages.example.com/dist/releases/0.2.0.202610140941/wheels/"
        f"yoke_{name}-0.2.0.202610140941-py3-none-any.whl"
        for name in ("contracts", "cli", "harness", "core")
    }
    assert "--extra-index-url" not in calls[0]
