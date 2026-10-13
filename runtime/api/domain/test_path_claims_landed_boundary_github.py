"""A landed merge's file list is read from GitHub whole, or refused by name."""

from __future__ import annotations

import pytest

from yoke_core.domain import path_claims_landed_boundary_github as reader
from yoke_core.domain.gh_rest_transport_errors import RestResponseTooLargeError

MERGE = "m" * 40
PARENT = "p" * 40


def _serve(monkeypatch, files, *, too_large_above: int = 0, parents=None) -> list:
    """Page ``files`` like GitHub's commit endpoint; record each query."""
    calls: list = []

    def _rest_get(path, *, token, query=None):
        size, page = int(query["per_page"]), int(query["page"])
        calls.append((size, page))
        if too_large_above and size > too_large_above:
            raise RestResponseTooLargeError("GitHub REST response too large")
        start = (page - 1) * size
        return {
            "sha": MERGE,
            "parents": [{"sha": PARENT}] if parents is None else parents,
            "files": files[start : start + size],
        }

    monkeypatch.setattr("yoke_core.domain.github_actions_rest.rest_get", _rest_get)
    return calls


def _files(count: int) -> list:
    return [{"filename": f"f{index}.py", "status": "added"} for index in range(count)]


def test_reads_every_page_until_a_short_one(monkeypatch):
    calls = _serve(monkeypatch, _files(301))

    parent, files = reader.merge_commit_files("o/r", "t", MERGE)

    assert parent == PARENT
    assert len(files) == 301
    assert calls == [(100, 1), (100, 2), (100, 3), (100, 4)]


def test_full_last_page_is_confirmed_by_an_empty_one(monkeypatch):
    calls = _serve(monkeypatch, _files(200))

    _parent, files = reader.merge_commit_files("o/r", "t", MERGE)

    assert len(files) == 200
    assert calls[-1] == (100, 3)


def test_oversized_page_is_reread_in_smaller_pages(monkeypatch):
    calls = _serve(monkeypatch, _files(25), too_large_above=10)

    _parent, files = reader.merge_commit_files("o/r", "t", MERGE)

    assert [f["filename"] for f in files] == [f"f{i}.py" for i in range(25)]
    assert calls == [(100, 1), (10, 1), (10, 2), (10, 3)]


def test_single_file_too_large_is_refused_with_recovery(monkeypatch):
    _serve(monkeypatch, _files(3), too_large_above=-1)

    with pytest.raises(reader.LandedBoundaryUnprovable, match="fetched the merge"):
        reader.merge_commit_files("o/r", "t", MERGE)


def test_list_at_githubs_ceiling_is_never_treated_as_complete(monkeypatch):
    _serve(monkeypatch, _files(reader.GITHUB_COMMIT_FILE_LIMIT))

    with pytest.raises(reader.LandedBoundaryUnprovable, match="may be incomplete"):
        reader.merge_commit_files("o/r", "t", MERGE)


def test_missing_parent_is_refused(monkeypatch):
    _serve(monkeypatch, _files(1), parents=[])

    with pytest.raises(reader.LandedBoundaryUnprovable, match="no parent"):
        reader.merge_commit_files("o/r", "t", MERGE)


def test_missing_commit_is_refused(monkeypatch):
    monkeypatch.setattr(
        "yoke_core.domain.github_actions_rest.rest_get", lambda *_a, **_k: None
    )

    with pytest.raises(reader.LandedBoundaryUnprovable, match="has no commit"):
        reader.merge_commit_files("o/r", "t", MERGE)
