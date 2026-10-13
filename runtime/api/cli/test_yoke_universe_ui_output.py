"""Browser admission stays private in every UI command output mode."""

from __future__ import annotations

import json

import pytest

from yoke_cli.commands import universe_ui as commands
from yoke_cli.config.hosted_machine_browser import BrowserOpenResult


@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize("mode", ["local", "self-host"])
@pytest.mark.parametrize(
    "outcome",
    ["opened", "disabled", "agent", "unregistered-agent", "headless", "exception"],
)
def test_admission_only_reaches_human_browser(
    monkeypatch, capsys, json_mode, mode, outcome
):
    secret = "private-admission-secret"
    url = (
        f"http://127.0.0.1:8688/?token={secret}"
        if mode == "local"
        else f"https://team.example/auth/browser-sign-in#selector.{secret}"
    )
    report = {
        "mode": mode,
        "env": "test",
        "running": True,
        "serving": True,
        "pid": 1234,
        "private_url": url,
    }
    monkeypatch.setattr(commands, "self_host_report", lambda **_: dict(report))
    monkeypatch.setattr(
        commands,
        "_resolve_session_id",
        lambda: "agent-session" if outcome == "agent" else None,
    )
    monkeypatch.setattr(
        commands,
        "nearest_harness_family",
        lambda: "codex" if outcome == "unregistered-agent" else None,
    )
    seen = []

    def open_browser(admission):
        seen.append(admission)
        if outcome == "exception":
            raise OSError(f"could not open {admission}")
        return BrowserOpenResult(
            opened=outcome == "opened",
            reason=f"browser_display_unavailable: {admission}",
        )

    monkeypatch.setattr(commands, "open_url", open_browser)
    args = ["--json"] if json_mode else []
    if outcome == "disabled":
        args.append("--no-browser")
    assert commands.ui_up(args) == (1 if outcome in {"headless", "exception"} else 0)
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert secret not in output
    assert url not in output
    assert "private_url" not in output
    assert "read-only" not in output
    assert seen == (
        [] if outcome in {"disabled", "agent", "unregistered-agent"} else [url]
    )
    if outcome != "opened":
        assert "your own terminal" in output
        assert "browser_" in output
    if json_mode:
        result = json.loads(captured.out)
        assert result["browser_opened"] is (outcome == "opened")
        assert result["ok"] is (outcome not in {"headless", "exception"})


@pytest.mark.parametrize("json_mode", [False, True])
def test_down_cannot_print_an_admission_url(monkeypatch, capsys, json_mode):
    monkeypatch.setattr(
        commands.daemon,
        "down",
        lambda: {"stopped": False, "private_url": "http://localhost/?token=secret"},
    )
    assert commands.ui_down(["--json"] if json_mode else []) == 0
    output = capsys.readouterr().out
    assert "secret" not in output
    assert "private_url" not in output
