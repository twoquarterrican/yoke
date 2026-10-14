"""A session's usage totals include every child agent it ran.

Each harness keeps a child agent's consumption outside the parent's own
record. These fixtures pair one parent artifact with one child artifact
in the shape each harness writes, and check that the reading is their
sum and that a statement repeated across the two is counted once. The
Cursor case, where a child's turn arrives as its own hook payload, lives
with the other Cursor payload tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from yoke_contracts.session_usage_facts import USAGE_COMPLETE, USAGE_PARTIAL
from yoke_harness.codex_usage_attestation import CHILD_ROLLOUT_MISSING_REASON
from yoke_harness.usage_attestation import attest_session_usage
from runtime.harness.session_usage_test_support import (  # noqa: F401
    append_rows,
    claude_row,
    codex_token_count,
    codex_turn_context,
    machine_home,
    write_rows,
)


def _claude_session(tmp_path: Path) -> tuple[Path, Path]:
    transcript = tmp_path / "session-1.jsonl"
    child_dir = tmp_path / "session-1" / "subagents"
    child_dir.mkdir(parents=True)
    return transcript, child_dir / "agent-a1.jsonl"


def _read_claude(transcript: Path):
    return attest_session_usage(
        "claude-code",
        {"session_id": "session-1", "transcript_path": str(transcript)},
        transcript_path=str(transcript),
    )


def test_claude_child_transcript_adds_to_the_session_total(tmp_path: Path) -> None:
    transcript, child = _claude_session(tmp_path)
    write_rows(transcript, [claude_row("msg_parent")])
    write_rows(child, [claude_row("msg_child", "claude-haiku-5", output_tokens=7)])

    usage = _read_claude(transcript)

    assert usage.status == USAGE_COMPLETE
    by_model = {entry.model: entry for entry in usage.models}
    assert by_model["claude-opus-5"].output == 100
    assert by_model["claude-haiku-5"].output == 7


def test_claude_message_repeated_across_files_is_counted_once(tmp_path: Path) -> None:
    """A child forked from the parent's context repeats the parent's rows."""
    transcript, child = _claude_session(tmp_path)
    write_rows(transcript, [claude_row("msg_shared")])
    write_rows(child, [claude_row("msg_shared"), claude_row("msg_child")])

    usage = _read_claude(transcript)

    assert usage.models[0].output == 200


def test_claude_each_file_resumes_from_its_own_offset(tmp_path: Path) -> None:
    transcript, child = _claude_session(tmp_path)
    write_rows(transcript, [claude_row("msg_parent")])
    write_rows(child, [claude_row("msg_child_1")])
    _read_claude(transcript)

    append_rows(child, [claude_row("msg_child_2")])
    usage = _read_claude(transcript)
    again = _read_claude(transcript)

    assert usage.models[0].output == 300
    assert again.models[0].output == 300


def test_claude_child_written_after_the_first_read_is_folded(tmp_path: Path) -> None:
    transcript, child = _claude_session(tmp_path)
    write_rows(transcript, [claude_row("msg_parent")])
    _read_claude(transcript)

    write_rows(child, [claude_row("msg_child")])
    usage = _read_claude(transcript)

    assert usage.models[0].output == 200


def _spawn(child_thread: str) -> dict:
    """The parent rollout row that names a child thread."""
    return {
        "type": "event_msg",
        "payload": {
            "type": "item_completed",
            "item": {
                "type": "SubAgentActivity",
                "kind": "started",
                "agent_thread_id": child_thread,
            },
        },
    }


def _read_codex(rollouts: dict[str, Path], monkeypatch: pytest.MonkeyPatch):
    from yoke_harness.hooks import identity_codex_runtime

    monkeypatch.setattr(
        identity_codex_runtime,
        "codex_transcript_candidates",
        lambda thread_id, **kwargs: (
            [rollouts[thread_id]] if thread_id in rollouts else []
        ),
    )
    return attest_session_usage(
        "codex", {"session_id": "codex-1", "thread_id": "parent"}
    )


def test_codex_child_thread_adds_to_the_session_total(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = write_rows(
        tmp_path / "rollout-parent.jsonl",
        [
            codex_turn_context("gpt-6"),
            codex_token_count(input_tokens=1_000, cached=400, output=50),
            _spawn("child"),
            _spawn("child"),
            codex_token_count(input_tokens=2_000, cached=900, output=80),
        ],
    )
    child = write_rows(
        tmp_path / "rollout-child.jsonl",
        [
            _spawn("child"),
            codex_turn_context("gpt-6-mini"),
            codex_token_count(input_tokens=300, cached=100, output=20),
        ],
    )

    usage = _read_codex({"parent": parent, "child": child}, monkeypatch)
    again = _read_codex({"parent": parent, "child": child}, monkeypatch)

    assert usage.status == USAGE_COMPLETE
    by_model = {entry.model: entry for entry in again.models}
    assert (by_model["gpt-6"].input, by_model["gpt-6"].output) == (1_100, 80)
    assert (by_model["gpt-6-mini"].input, by_model["gpt-6-mini"].output) == (200, 20)
    assert not again.cost_caveat


def test_codex_child_named_before_its_rollout_exists_is_partial_then_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = write_rows(
        tmp_path / "rollout-parent.jsonl",
        [
            codex_turn_context("gpt-6"),
            _spawn("child"),
            codex_token_count(input_tokens=1_000, output=50),
        ],
    )

    pending = _read_codex({"parent": parent}, monkeypatch)
    child = write_rows(
        tmp_path / "rollout-child.jsonl",
        [codex_turn_context("gpt-6"), codex_token_count(input_tokens=10, output=5)],
    )
    usage = _read_codex({"parent": parent, "child": child}, monkeypatch)

    assert pending.status == USAGE_PARTIAL
    assert pending.reason == CHILD_ROLLOUT_MISSING_REASON
    assert usage.status == USAGE_COMPLETE
    assert usage.models[0].output == 55
