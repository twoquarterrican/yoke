"""The installed CLI follows each release the prod relay starts on."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from yoke_cli.commands.adapters import session_control_relay_release as release_cli
from yoke_cli.config import (
    distribution,
    install_binding,
    operator_cli_release_follow as follow,
)
from yoke_cli.config import self_update, session_relay_instance
from yoke_cli.self_host import release_target
from yoke_cli.transport import installed_cli_staleness
from yoke_contracts.install_binding import KIND_PACKAGED_WHEEL
from yoke_core.tools import session_relay_release
from yoke_harness import session_relay_daemon


def _cli(tmp_path: Path, versions: list[str], *, installs: bool = True):
    yoke = tmp_path / "yoke"
    yoke.write_text("", encoding="utf-8")
    calls: list[list[str]] = []

    def run(argv, **_kwargs):
        calls.append(list(argv))
        if argv[1] == "--version":
            return subprocess.CompletedProcess(argv, 0, stdout=versions[0] + "\n")
        if installs:
            versions.pop(0)
        return subprocess.CompletedProcess(
            argv, 1 - installs, stdout="installer said no"
        )

    return yoke, calls, run


def test_behind_cli_installs_exactly_the_observed_release(tmp_path) -> None:
    yoke, calls, run = _cli(tmp_path, ["0.1.1+launch.616", "0.1.1+launch.621"])
    record = follow.follow_release(
        "v0.1.1+launch.621", tmp_path, run=run, executable=yoke
    )
    assert record["outcome"] == "updated"
    assert [str(yoke), "update", "--version", "0.1.1+launch.621", "--json"] in calls
    stored = json.loads((tmp_path / follow.FOLLOW_RECORD_NAME).read_text())
    assert stored["after"] == "0.1.1+launch.621"


def test_current_cli_is_left_alone(tmp_path) -> None:
    yoke, calls, run = _cli(tmp_path, ["0.1.1+launch.621"])
    record = follow.follow_release(
        "v0.1.1+launch.621", tmp_path, run=run, executable=yoke
    )
    assert record["outcome"] == "current"
    assert all(call[1] == "--version" for call in calls)


def test_failed_install_names_the_recovery(tmp_path, capsys) -> None:
    yoke, _calls, run = _cli(tmp_path, ["0.1.1+launch.616"], installs=False)
    record = follow.follow_release(
        "v0.1.1+launch.621", tmp_path, run=run, executable=yoke
    )
    assert record["outcome"] == "update_failed"
    err = capsys.readouterr().err
    assert "OPERATOR-CLI-FOLLOW-FAILED" in err
    assert "yoke update --version 0.1.1+launch.621" in err


def test_prod_relay_start_follows_its_pinned_release(monkeypatch, tmp_path) -> None:
    instance = SimpleNamespace(
        environment="prod",
        state_dir=tmp_path,
        follows_served_release=True,
        prod=True,
    )
    followed: list[str] = []
    monkeypatch.setattr(
        session_relay_instance, "resolve_relay_instance", lambda: instance
    )
    monkeypatch.setattr(
        session_relay_release,
        "relay_release_status",
        lambda **_k: SimpleNamespace(
            current=True,
            pinned_release="v0.1.1+launch.621",
            runtime_python=Path(sys.prefix) / "bin" / "python",
        ),
    )
    monkeypatch.setattr(
        follow, "follow_release", lambda release, _d: followed.append(release)
    )
    monkeypatch.setattr(session_relay_daemon, "serve_forever", lambda **_k: "served")
    assert release_cli.serve_release_daemon() == "served"
    assert followed == ["v0.1.1+launch.621"]


def test_update_installs_the_requested_version_from_the_recorded_origin(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("YOKE_MACHINE_CONFIG_FILE", str(tmp_path / "config.json"))
    distribution.save(origin="https://fork.example", channel="stable")
    monkeypatch.setattr(
        install_binding,
        "detect",
        lambda: {"kind": KIND_PACKAGED_WHEEL, "version": "1.0.0"},
    )
    monkeypatch.setattr(self_update.shutil, "which", lambda _: "/bin/yoke")
    monkeypatch.setattr(
        release_target,
        "channel_release_target",
        lambda **_k: release_target.ReleaseTarget(
            version="1.2.0",
            source_commit="c",
            image="i",
            base_url="https://fork.example",
            channel="stable",
            installer_url="https://fork.example/dist/install.py",
        ),
    )
    installed: list[str] = []

    def stop(target):
        installed.append(target.version)
        raise release_target.ReleaseTargetError("stop before fetching")

    monkeypatch.setattr(release_target, "fetch_installer", stop)
    try:
        self_update.run_update(version="v1.1.0+launch.7")
    except self_update.SelfUpdateError:
        pass
    assert installed == ["1.1.0+launch.7"]


def test_stale_cli_warns_once_and_only_against_prod(monkeypatch) -> None:
    monkeypatch.setattr(installed_cli_staleness, "_warned", False)
    stream = io.StringIO()
    kwargs = dict(server_version="0.1.1+launch.621", local_version="0.1.1+launch.616")
    assert not installed_cli_staleness.warn_if_behind_prod(
        prod=False, stream=stream, **kwargs
    )
    assert installed_cli_staleness.warn_if_behind_prod(
        prod=True, stream=stream, **kwargs
    )
    assert not installed_cli_staleness.warn_if_behind_prod(
        prod=True, stream=stream, **kwargs
    )
    assert "yoke update --version 0.1.1+launch.621" in stream.getvalue()


def test_current_cli_does_not_warn(monkeypatch) -> None:
    monkeypatch.setattr(installed_cli_staleness, "_warned", False)
    assert not installed_cli_staleness.warn_if_behind_prod(
        prod=True, server_version="0.1.1+launch.621", local_version="0.1.1+launch.621"
    )
