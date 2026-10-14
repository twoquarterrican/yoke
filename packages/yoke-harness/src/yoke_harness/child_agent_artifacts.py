"""Where each harness records the consumption of a session's child agents.

A session that delegates to child agents (subagents) is charged for every
call those children make, and none of the harnesses writes that usage
into the parent's own record. Each one keeps it somewhere else, so each
needs its own discovery; what is discovered then folds into the same
per-model totals as the parent's own calls, and is priced with them.

* **claude** — each child writes its own transcript under the parent
  transcript's stem: ``<stem>/subagents/agent-<id>.jsonl``, with the same
  assistant ``message.usage`` rows as the parent.
* **codex** — each child is its own thread with its own rollout and its
  own cumulative ``token_count``. The parent rollout names each child in
  a ``SubAgentActivity`` item's ``agent_thread_id``; a child names its
  own children the same way.
* **cursor** — child turns arrive as hook payloads flagged
  ``is_subagent_session``, already folded onto the container session id
  by payload parsing. There is no file to discover: the payload is the
  child's statement, and :mod:`yoke_harness.cursor_usage_attestation`
  folds it like any other turn.

Each branch only names where a child's usage is; it reads nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


#: Directory under a Claude transcript's stem that holds child transcripts.
CLAUDE_CHILD_DIRECTORY = "subagents"

#: File pattern of one Claude child-agent transcript.
CLAUDE_CHILD_TRANSCRIPT_GLOB = "agent-*.jsonl"

#: Codex rollout item naming a child thread the session spawned.
CODEX_CHILD_ITEM_TYPE = "SubAgentActivity"


def claude_child_transcripts(transcript: Path) -> list[Path]:
    """Every child transcript a Claude session has written, in name order."""
    directory = transcript.with_suffix("") / CLAUDE_CHILD_DIRECTORY
    try:
        return sorted(
            path
            for path in directory.glob(CLAUDE_CHILD_TRANSCRIPT_GLOB)
            if path.is_file()
        )
    except OSError:
        return []


def codex_child_thread_id(row: Mapping[str, Any]) -> str:
    """The child thread a Codex rollout row names, or ``""``."""
    payload = row.get("payload")
    item = payload.get("item") if isinstance(payload, dict) else None
    if not isinstance(item, dict) or item.get("type") != CODEX_CHILD_ITEM_TYPE:
        return ""
    thread_id = item.get("agent_thread_id")
    return thread_id.strip() if isinstance(thread_id, str) else ""


__all__ = [
    "CLAUDE_CHILD_DIRECTORY",
    "CLAUDE_CHILD_TRANSCRIPT_GLOB",
    "CODEX_CHILD_ITEM_TYPE",
    "claude_child_transcripts",
    "codex_child_thread_id",
]
