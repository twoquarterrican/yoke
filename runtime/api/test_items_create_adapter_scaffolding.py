"""CLI ``yoke items create`` refuses unscaffolded live-session callers."""

from __future__ import annotations

from yoke_cli.commands.adapters import items_create, items_create_policy as policy


def test_allow_operator_debug_without_ambient_session() -> None:
    assert policy.allow_low_level_items_create(
        dry_run=False,
        test_isolated=False,
        ambient_session_id=None,
        session_mode=None,
    )


def test_allow_dry_run_even_with_non_idea_session() -> None:
    assert policy.allow_low_level_items_create(
        dry_run=True,
        test_isolated=False,
        ambient_session_id="session-steer",
        session_mode="steer",
    )


def test_allow_test_isolation_even_with_non_idea_session() -> None:
    assert policy.allow_low_level_items_create(
        dry_run=False,
        test_isolated=True,
        ambient_session_id="session-dash",
        session_mode="dash",
    )


def test_allow_idea_mode_skill_owned_caller() -> None:
    assert policy.allow_low_level_items_create(
        dry_run=False,
        test_isolated=False,
        ambient_session_id="session-idea",
        session_mode=policy.IDEA_SESSION_MODE,
    )


def test_refuse_live_session_that_is_not_idea() -> None:
    assert not policy.allow_low_level_items_create(
        dry_run=False,
        test_isolated=False,
        ambient_session_id="session-steer",
        session_mode="steer",
    )


def test_adapter_refuses_non_idea_session_and_names_correct_paths(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(policy, "_is_test_isolation", lambda: False)
    monkeypatch.setattr(
        policy,
        "_ambient_session_id",
        lambda: "session-steer",
    )
    monkeypatch.setattr(
        policy,
        "_session_mode",
        lambda _sid: ("steer", None),
    )

    assert (
        items_create.items_create(
            [
                "Skip scaffolding",
                "issue",
                "--entry-surface",
                "harness_skill",
                "--execution-instructions-considered",
            ]
        )
        == 2
    )
    err = capsys.readouterr().err
    assert policy.ITEMS_CREATE_SKILL_SCAFFOLDING_REFUSAL in err
    assert "/yoke idea" in err
    assert "yoke items create TITLE dash --spec-file PATH" in err


def test_adapter_dispatches_when_session_mode_is_idea(monkeypatch) -> None:
    captured = {}

    def _dispatch(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(policy, "_is_test_isolation", lambda: False)
    monkeypatch.setattr(
        policy,
        "_ambient_session_id",
        lambda: "session-idea",
    )
    monkeypatch.setattr(
        policy,
        "_session_mode",
        lambda _sid: ("idea", None),
    )
    monkeypatch.setattr(items_create, "dispatch_create", _dispatch)

    assert (
        items_create.items_create(
            [
                "File through idea",
                "issue",
                "--entry-surface",
                "harness_skill",
                "--execution-instructions-considered",
            ]
        )
        == 0
    )
    assert captured["payload"]["workflow"] == "issue"


def test_adapter_dispatches_dry_run_without_reading_session_mode(
    monkeypatch,
) -> None:
    captured = {}

    def _dispatch(**kwargs):
        captured.update(kwargs)
        return 0

    def _fail_mode(_sid: str):
        raise AssertionError("dry-run must not consult session mode")

    monkeypatch.setattr(policy, "_is_test_isolation", lambda: False)
    monkeypatch.setattr(
        policy,
        "_ambient_session_id",
        lambda: "session-steer",
    )
    monkeypatch.setattr(policy, "_session_mode", _fail_mode)
    monkeypatch.setattr(items_create, "dispatch_create", _dispatch)

    assert items_create.items_create(["Preview only", "issue", "--dry-run"]) == 0
    assert captured["payload"]["dry_run"] is True


def test_adapter_refuses_when_session_identity_cannot_be_read(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(policy, "_is_test_isolation", lambda: False)
    monkeypatch.setattr(
        policy,
        "_ambient_session_id",
        lambda: "session-missing",
    )
    monkeypatch.setattr(
        policy,
        "_session_mode",
        lambda _sid: (
            None,
            "session id is required Recover with: yoke sessions identity",
        ),
    )

    assert items_create.items_create(["Needs identity", "issue"]) == 2
    err = capsys.readouterr().err
    assert "yoke sessions identity" in err
