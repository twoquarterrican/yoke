"""Parse product CLI smoke output and evaluate process and filesystem facts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional
from yoke_core.tools.checkout_clean_room_smoke_helpers import CommandResult


def parse_json_output(stdout: str) -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(stdout)
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def issue_codes(payload: Optional[Mapping[str, Any]]) -> set:
    if not isinstance(payload, Mapping):
        return set()
    return {
        str(issue.get("code") or "")
        for issue in payload.get("issues") or []
        if isinstance(issue, Mapping)
    }


def dir_entries(path: Path) -> list[str]:
    if not path.is_dir():
        return []
    return sorted(entry.name for entry in path.iterdir())


def _expect_nonzero(result: CommandResult) -> list[str]:
    if result.returncode == 0:
        return [f"{result.step}: expected a non-zero exit, got 0"]
    return []


def _combined_output(result: CommandResult) -> str:
    return f"{result.stdout}\n{result.stderr}"


def _owner_only_mode(path: Path) -> Optional[int]:
    if not path.is_file():
        return None
    return path.stat().st_mode & 0o777
