"""Dash filing options preserve provenance, posture, attestation and priority."""

import pytest

from yoke_cli.commands.adapters import dash_file, items_create


def _capture(monkeypatch, module):
    captured = {}

    def dispatch(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(items_create, "dispatch_create", dispatch)
    return captured


def test_dash_filing_uses_cli_provenance_and_tightening_posture(monkeypatch):
    captured = _capture(monkeypatch, dash_file)

    assert (
        dash_file.dash_file(
            [
                "Tighten footer",
                "Fix the footer copy.",
                "--project",
                "yoke",
                "--path-claims",
                "--approval-on-done",
                "--deployment",
                "--execution-instructions-considered",
            ]
        )
        == 0
    )

    assert captured["payload"] == {
        "title": "Tighten footer",
        "dry_run": False,
        "spec": "Fix the footer copy.",
        "workflow": "dash",
        "entry_surface": "cli",
        "workflow_posture": {
            "path_claims": True,
            "approval_on_done": True,
            "deployment": True,
        },
        "project": "yoke",
        "execution_instructions_considered": True,
    }


def test_dash_filing_never_attests_for_the_caller(monkeypatch):
    captured = _capture(monkeypatch, dash_file)

    assert dash_file.dash_file(["Tighten footer", "Fix the footer copy."]) == 0

    # The flag records what the filer did before authoring; an adapter
    # that defaulted it to true would attest a read that never happened.
    assert captured["payload"]["execution_instructions_considered"] is False


def test_dash_filing_help_lists_priority_choices(capsys):
    with pytest.raises(SystemExit) as raised:
        dash_file.dash_file(["--help"])
    assert raised.value.code == 0
    help_text = capsys.readouterr().out
    assert "{high,medium,low}" in help_text
    assert "Priority bucket: high, medium, or low." in help_text


def test_dash_filing_accepts_named_priority(monkeypatch):
    captured = _capture(monkeypatch, dash_file)

    assert (
        dash_file.dash_file(
            [
                "Tighten footer",
                "Fix the footer copy.",
                "--priority",
                "high",
            ]
        )
        == 0
    )
    assert captured["payload"]["priority"] == "high"


def test_dash_filing_rejects_unknown_priority(capsys):
    assert (
        dash_file.dash_file(
            [
                "Tighten footer",
                "Fix the footer copy.",
                "--priority",
                "P2",
            ]
        )
        == 2
    )
    err = capsys.readouterr().err
    assert "invalid choice" in err
    assert "P2" in err
