"""File Budget reading of framework route paths with ``[ ] ( ) @ +``."""

from __future__ import annotations

import pytest

from yoke_core.domain.file_budget_paths import (
    extract_file_budget_paths,
    is_path_token,
)
from yoke_core.domain.file_budget_sizing import parse_file_budget_sizing

ROUTE_PATHS = [
    "webapp/app/docs/[[...slug]]/page.tsx",
    "webapp/app/blog/[...slug]/page.tsx",
    "webapp/app/orgs/[id]/page.tsx",
    "webapp/app/(marketing)/page.tsx",
    "webapp/app/@modal/page.tsx",
    "web/src/routes/+page.svelte",
]


@pytest.mark.parametrize("path", ROUTE_PATHS)
def test_route_path_is_path_token(path):
    assert is_path_token(path) is True


@pytest.mark.parametrize(
    "token",
    [
        ">/dev/null",
        "2>&1",
        "a/b | c",
        "a/b&c",
        "a/b>c",
        "app/docs/[[...slug]] /page.tsx",
        "app/[id]/",
    ],
)
def test_shell_fragments_and_directories_stay_rejected(token):
    assert is_path_token(token) is False


def test_extract_reads_route_paths_in_order():
    spec = "## File Budget\n" + "".join(f"- `{p}` — route\n" for p in ROUTE_PATHS)
    assert extract_file_budget_paths(spec) == ROUTE_PATHS


def test_sizing_parses_route_paths():
    spec = "## File Budget\n" + "".join(
        f"- `{p}` — current 12 lines; remaining headroom 338; "
        "at-or-over-limit: false; responsibility: route\n"
        for p in ROUTE_PATHS
    )
    assert [entry.path for entry in parse_file_budget_sizing(spec)] == ROUTE_PATHS
