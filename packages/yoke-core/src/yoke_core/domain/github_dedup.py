"""Find a GitHub issue with the exact outgoing title and body.

GitHub title search is fuzzy. Candidates are adopted only when both fields
match after whitespace normalization; otherwise creation owns the new issue.

Searches key on the bracketed item-ref prefix of the title, so an epic parent
and every child task issue share one query. A sync passes one
``IssueSearchCache`` through its creates so that query runs once per sync:
the Search API's low rate limit otherwise turns per-child searches into
backoff waits.
"""

from __future__ import annotations

import sys
from typing import Optional, TextIO

from yoke_core.domain import github_rest

# Search query -> candidates, or None when that search failed this sync.
IssueSearchCache = dict[str, Optional[list[github_rest.Issue]]]


def _search_title(title: str) -> str:
    return title.split("]", 1)[0] + "]" if title.startswith("[") else title


def _search_candidates(
    title: str,
    *,
    project: str,
    stderr: TextIO,
    cache: Optional[IssueSearchCache],
) -> Optional[list[github_rest.Issue]]:
    query = f"{_search_title(title)} in:title is:issue"
    if cache is not None and query in cache:
        return cache[query]
    candidates: Optional[list[github_rest.Issue]]
    try:
        candidates = github_rest.list_issues(project=project, search=query, limit=100)
    except github_rest.RestTransportError as exc:
        print(
            f"Warning: github_dedup_search_failed for {query!r}: {exc}. "
            "Skipping reuse for issues this sync creates under that search; "
            "creation will make new issues. "
            "Check GitHub access and retry sync if creation fails.",
            file=stderr,
        )
        candidates = None
    if cache is not None:
        cache[query] = candidates
    return candidates


def search_existing_issue(
    title: str,
    body: str,
    *,
    project: str,
    stderr: Optional[TextIO] = None,
    cache: Optional[IssueSearchCache] = None,
) -> Optional[tuple[str, str]]:
    """Return the first full content match, or None when reuse is unproven.

    ``cache`` shares search results across the creates of one sync; a failed
    search is cached too, so it is not retried for each later issue.
    """
    candidates = _search_candidates(
        title,
        project=project,
        stderr=stderr if stderr is not None else sys.stderr,
        cache=cache,
    )
    if not candidates:
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
