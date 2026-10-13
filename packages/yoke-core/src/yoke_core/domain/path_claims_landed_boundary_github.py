"""A landed merge's complete changed-file list, read from GitHub.

A hosted control plane holds no checkout, so it reads what a merge changed
from the repository provider. The commit endpoint answers that for a merge
commit as its diff against the first parent, which is exactly what the item
put on its target. Unlike the compare endpoint, whose file list stops at 300
with no way to page further, the commit endpoint pages its file list up to
GitHub's documented 3000-file ceiling. A list that reaches that ceiling may
be missing paths, so it is refused rather than treated as complete.
"""

from __future__ import annotations

from typing import Any, List, Mapping, Optional, Tuple

from yoke_contracts.github_app_installation_permissions import (
    GITHUB_CONTENTS_READ_PERMISSION_LEVELS,
)

#: GitHub stops listing a commit's changed files here; a list this long may
#: be incomplete.
GITHUB_COMMIT_FILE_LIMIT = 3000

#: Page sizes tried in order. A page whose patches push the response past
#: the transport's size ceiling is re-read in smaller pages; each size
#: divides the one before it so the file offset always lands on a page.
COMMIT_FILE_PAGE_SIZES = (100, 10, 1)

_RECOVERY = (
    "rerun the close-out on a machine whose project checkout has fetched "
    "the merge, which reads the diff from git instead"
)


class LandedBoundaryUnprovable(RuntimeError):
    """The landed merge's diff could not be read from any source."""


def _commit_page(
    repo: str, token: str, merge_sha: str, *, size: int, page: int
) -> Mapping[str, Any]:
    from yoke_core.domain.github_actions_rest import rest_get

    body = rest_get(
        f"/repos/{repo}/commits/{merge_sha}",
        query={"per_page": str(size), "page": str(page)},
        token=token,
    )
    if not isinstance(body, Mapping):
        raise LandedBoundaryUnprovable(f"GitHub has no commit {merge_sha} in {repo}")
    return body


def merge_commit_files(
    repo: str, token: str, merge_sha: str
) -> Tuple[str, List[Mapping[str, Any]]]:
    """Return ``(first_parent, files)`` for ``merge_sha``, every page read."""
    from yoke_core.domain.gh_rest_transport_errors import RestResponseTooLargeError

    files: List[Mapping[str, Any]] = []
    parent = ""
    sizes = list(COMMIT_FILE_PAGE_SIZES)
    while True:
        size = sizes[0]
        try:
            body = _commit_page(
                repo, token, merge_sha, size=size, page=len(files) // size + 1
            )
        except RestResponseTooLargeError as exc:
            if len(sizes) == 1:
                raise LandedBoundaryUnprovable(
                    f"GitHub's diff of merge {merge_sha} holds a single file "
                    f"too large to read ({exc}); {_RECOVERY}"
                ) from exc
            sizes.pop(0)
            continue
        if not parent:
            parents = body.get("parents") or []
            parent = str((parents[0] or {}).get("sha") or "") if parents else ""
            if not parent:
                raise LandedBoundaryUnprovable(
                    f"GitHub has no parent for merge {merge_sha} in {repo}"
                )
        page_files = [f for f in body.get("files") or [] if isinstance(f, Mapping)]
        files.extend(page_files)
        if len(files) >= GITHUB_COMMIT_FILE_LIMIT:
            raise LandedBoundaryUnprovable(
                f"merge {merge_sha} changes {len(files)} or more files, the "
                f"{GITHUB_COMMIT_FILE_LIMIT}-file ceiling GitHub lists for a "
                f"commit, so the list may be incomplete; {_RECOVERY}"
            )
        if len(page_files) < size:
            return parent, files


def diff_from_github(
    conn: Any, project_slug: str, merge_sha: str
) -> Optional[Tuple[str, List[str], List[Tuple[str, str]]]]:
    """``(first_parent, touched, renames)``, or ``None`` with no capability."""
    from yoke_core.domain.project_github_auth import (
        MissingCapability,
        ProjectGithubAuthError,
        resolve_project_github_auth,
    )

    try:
        auth = resolve_project_github_auth(
            project_slug,
            conn=conn,
            required_permissions=GITHUB_CONTENTS_READ_PERMISSION_LEVELS,
        )
    except MissingCapability:
        return None
    except ProjectGithubAuthError as exc:
        raise LandedBoundaryUnprovable(
            f"the project's GitHub capability is unusable: {exc.code}: {exc}"
        ) from exc
    try:
        parent, files = merge_commit_files(auth.repo, auth.token, merge_sha)
    except LandedBoundaryUnprovable:
        raise
    except Exception as exc:
        raise LandedBoundaryUnprovable(
            f"GitHub could not read merge {merge_sha}: {type(exc).__name__}: {exc}"
        ) from exc
    touched = list(dict.fromkeys(str(f.get("filename") or "") for f in files))
    renames = [
        (str(f["previous_filename"]), str(f.get("filename") or ""))
        for f in files
        if f.get("status") == "renamed" and f.get("previous_filename")
    ]
    return parent, [path for path in touched if path], renames


__all__ = [
    "COMMIT_FILE_PAGE_SIZES",
    "GITHUB_COMMIT_FILE_LIMIT",
    "LandedBoundaryUnprovable",
    "diff_from_github",
    "merge_commit_files",
]
