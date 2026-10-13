"""Find a GitHub issue with the exact outgoing title and body.

GitHub title search is fuzzy. Candidates are adopted only when both fields
match after whitespace normalization; otherwise creation owns the new issue.
"""

from __future__ import annotations

import sys
from typing import Optional, TextIO

from yoke_core.domain import github_rest


def search_existing_issue(
    title: str,
    body: str,
    *,
    project: str,
    stderr: Optional[TextIO] = None,
) -> Optional[tuple[str, str]]:
    """Return the first full content match, or None when reuse is unproven."""
    err = stderr if stderr is not None else sys.stderr
    search_title = title.split("]", 1)[0] + "]" if title.startswith("[") else title
    try:
        candidates = github_rest.list_issues(
            project=project,
            search=f"{search_title} in:title is:issue",
            limit=100,
        )
    except github_rest.RestTransportError as exc:
        print(
            f"Warning: github_dedup_search_failed for {title!r}: {exc}. "
            "Skipping reuse; creation will make a new issue. "
            "Check GitHub access and retry sync if creation fails.",
            file=err,
        )
        return None

    expected_title = " ".join(title.split())
    expected_body = " ".join(body.split())
    for entry in candidates:
        if (
            entry.number > 0
            and not entry.is_pull_request
            and " ".join(entry.title.split()) == expected_title
            and " ".join(entry.body.split()) == expected_body
        ):
            return str(entry.number), entry.title
    return None
