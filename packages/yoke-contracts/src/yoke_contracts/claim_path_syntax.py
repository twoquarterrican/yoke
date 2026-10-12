"""Which operator-supplied path-claim arguments can name a repo path.

Shared by the CLI, which refuses before any network call, and the server
resolver, which refuses for every other caller before any path is resolved
or planned. Both surfaces carry the same named reason and recovery step.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

from yoke_contracts.path_snapshot import invalid_project_relative_paths

PATH_MALFORMED = "path_malformed"
PATH_NOT_PROJECT_RELATIVE = "path_not_project_relative"

# Quotes and stray shell quoting, glob wildcards and Windows separators never
# name a committed repo file the registry would hold. Brackets stay legal:
# routed frameworks commit files such as ``app/[slug]/page.tsx``.
_MALFORMED_PATH_CHARS = frozenset("'\"`*?\\")


def malformed_claim_paths(paths: Iterable[str]) -> List[str]:
    """Return paths carrying quoting, wildcards, backslashes or control bytes."""
    return [
        path
        for path in paths
        if any(
            char in _MALFORMED_PATH_CHARS or ord(char) < 32 or ord(char) == 127
            for char in path
        )
    ]


def malformed_paths_message(paths: Sequence[str]) -> str:
    return (
        "path claim targets must be literal repo paths; these contain quote, "
        "wildcard, backslash or control characters: "
        f"{', '.join(repr(path) for path in paths)}. Re-run with each literal "
        "path, forward slashes only, no wildcards, and the whole --paths value "
        "quoted once by the shell."
    )


def non_project_relative_paths_message(paths: Sequence[str]) -> str:
    return (
        "path claim targets must be project-relative repo paths; outside-repo "
        f"paths are not claimable: {', '.join(paths)}. Re-run with each path "
        "written from the repository root, with no leading '/' and no '.', "
        "'..' or empty segments."
    )


def claim_path_refusal(paths: Sequence[str]) -> Optional[Tuple[str, str]]:
    """Return ``(code, message)`` refusing the whole set, or ``None``."""
    malformed = malformed_claim_paths(paths)
    if malformed:
        return PATH_MALFORMED, malformed_paths_message(malformed)
    invalid = invalid_project_relative_paths(paths)
    if invalid:
        return PATH_NOT_PROJECT_RELATIVE, non_project_relative_paths_message(invalid)
    return None


__all__ = [
    "PATH_MALFORMED",
    "PATH_NOT_PROJECT_RELATIVE",
    "claim_path_refusal",
    "malformed_claim_paths",
    "malformed_paths_message",
    "non_project_relative_paths_message",
]
