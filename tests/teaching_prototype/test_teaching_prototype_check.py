"""The teaching prototype stays consistent with its model and live registries."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "docs" / "teaching" / "tools"


@pytest.fixture
def tools(monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS))
    import model
    import inventory
    import privacy
    import render

    return model, inventory, privacy, render


def test_model_builds_valid_views():
    result = subprocess.run(
        [sys.executable, str(TOOLS / "build.py"), "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "check passed" in result.stdout


def test_validate_names_dangling_references_and_unmapped_plan_rows(tools):
    model, *_ = tools
    loaded = model.Model()
    loaded.concepts["a"] = {
        "id": "a",
        "title": "A",
        "status": "draft-copy",
        "plan_refs": ["PLAN.missing"],
        "commands": ["yoke nope"],
        "sources": ["no/such/file.md"],
        "file": "c.json",
    }
    loaded.plan_rows["PLAN.1"] = {
        "id": "PLAN.1",
        "status": "approved",
        "file": "p.json",
    }
    loaded.gaps["g"] = {"id": "g", "status": "open", "file": "gaps.json"}
    live = {"commands": {"yoke real"}, "functions": set(), "skills": set()}
    model.validate(loaded, live, {"README.md"})
    codes = sorted(problem.code for problem in loaded.problems)
    assert codes == [
        "DANGLING_REFERENCE",
        "DANGLING_REFERENCE",
        "DANGLING_SOURCE",
        "PLAN_ROW_UNMAPPED",
        "UNKNOWN_STATUS",
    ]


def test_coverage_counts_only_direct_mappings(tools):
    model, *_ = tools
    loaded = model.Model()
    loaded.concepts["parent"] = {"plan_refs": ["PLAN.1"]}
    loaded.concepts["parent/child"] = {}
    assert model.coverage(loaded) == {"parent": ["PLAN.1"], "parent/child": []}


@pytest.mark.parametrize(
    "line",
    [
        "see /" + "Users/someone/notes.md",
        "Mobile " + "Documents/Docs",
        "captured at /" + "tmp/capture.txt",
        "session 123e4567-e89b-12d3-a456-426614174000",
    ],
)
def test_privacy_patterns_flag_private_material(tools, line):
    _, _, privacy, _ = tools
    assert any(pattern.search(line) for _, pattern in privacy.PATTERNS)


def test_privacy_patterns_allow_repository_paths(tools):
    _, _, privacy, _ = tools
    line = "docs/teaching/model/gaps.json and packages/yoke-core/src"
    assert not any(pattern.search(line) for _, pattern in privacy.PATTERNS)


def test_strategy_entries_lists_every_required_row(tools, tmp_path):
    _, inventory, _, _ = tools
    content = "\n".join(
        [
            "# JOURNEYS",
            "## Locked principles",
            "1. **One.**",
            "## Situations catalog",
            "| # | Situation |",
            "| 1 | Install |",
            "## Also owned here",
            "- **Work.**",
            "## Open questions",
            "1. Why?",
        ]
    )
    saved = tmp_path / "journeys.json"
    saved.write_text(
        json.dumps(
            {"result": {"slug": "JOURNEYS", "content": content, "updated_at": "now"}}
        )
    )
    slug, updated_at, ids = inventory.strategy_entries(saved)
    assert (slug, updated_at) == ("JOURNEYS", "now")
    assert ids == [
        "JOURNEYS.locked-principles",
        "JOURNEYS.principle-1",
        "JOURNEYS.situations-catalog",
        "JOURNEYS.situation-1",
        "JOURNEYS.also-owned-here",
        "JOURNEYS.owned-1",
        "JOURNEYS.open-questions",
        "JOURNEYS.question-1",
    ]


def test_wrapped_line_count_uses_eighty_columns(tools):
    *_, render = tools
    assert render.wrapped_lines("x" * 80 + "\n" + "y" * 81 + "\n\n") == 4
    assert all(len(line) <= 80 for line in render.wrap("word " * 60))


def test_check_does_not_depend_on_local_views(tools, monkeypatch, tmp_path):
    import build

    local_views = tmp_path / "views"
    monkeypatch.setattr(build, "VIEWS_ROOT", local_views)
    assert build.main(["--check"]) == 0
    assert not local_views.exists()
    local_views.mkdir()
    stale = local_views / "unexpected.html"
    stale.write_text("obsolete output")
    assert build.main(["--check"]) == 0
    assert stale.read_text() == "obsolete output"


def test_build_recreates_html_and_stylesheet(tools, monkeypatch, tmp_path):
    import build

    monkeypatch.setattr(build, "VIEWS_ROOT", tmp_path / "views")
    monkeypatch.setattr(build, "model_files", lambda: [])
    assert build.main([]) == 0
    assert (tmp_path / "views/index.html").read_text().startswith("<!doctype html>")
    assert (tmp_path / "views/style.css").read_text() == (
        TOOLS / "style.css"
    ).read_text()


def test_generated_views_are_untracked_and_ignored():
    tracked = subprocess.check_output(
        ["git", "ls-files", "docs/teaching/views"], cwd=REPO, text=True
    )
    assert not tracked
    result = subprocess.run(
        ["git", "check-ignore", "docs/teaching/views/index.html"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_check_refuses_invalid_model_with_recovery(tools, monkeypatch, capsys):
    import build

    loaded = build.load()
    loaded.concepts["documentation"]["status"] = "invalid"
    monkeypatch.setattr(build, "load", lambda: loaded)
    assert build.main(["--check"]) == 1
    output = capsys.readouterr().out
    assert "UNKNOWN_STATUS" in output
    assert "Fix the model" in output
    assert "--check" in output
