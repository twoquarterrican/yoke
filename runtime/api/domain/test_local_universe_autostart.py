"""Starting a stopped embedded Postgres before a step that needs it."""

from __future__ import annotations

import pytest

from yoke_core.domain import local_universe, local_universe_autostart


def _state(monkeypatch, *, initialized: bool, running: bool) -> list:
    started: list = []
    monkeypatch.setattr(
        local_universe,
        "status",
        lambda _spec=None: {
            "root": "/machine/universe",
            "initialized": initialized,
            "running": running,
        },
    )
    monkeypatch.setattr(
        local_universe, "start", lambda spec=None, emit=None: started.append(spec)
    )
    return started


def test_initialized_stopped_cluster_is_started_after_a_restart(monkeypatch) -> None:
    started = _state(monkeypatch, initialized=True, running=False)
    lines: list[str] = []
    local_universe_autostart.ensure_running(emit=lines.append)
    assert started == [None]
    assert "yoke local-postgres start" in lines[0]


def test_running_cluster_is_left_alone(monkeypatch) -> None:
    started = _state(monkeypatch, initialized=True, running=True)
    local_universe_autostart.ensure_running()
    assert started == []


def test_uninitialized_cluster_refuses_with_the_command_that_makes_it(
    monkeypatch,
) -> None:
    started = _state(monkeypatch, initialized=False, running=False)
    with pytest.raises(local_universe.LocalUniverseError, match="local-postgres start"):
        local_universe_autostart.ensure_running()
    assert started == []
