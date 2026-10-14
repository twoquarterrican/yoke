"""The retired-term scan's prefilters answer exactly what the regex would."""

from __future__ import annotations

import re

import pytest

from yoke_project_checks import check_obsoleted_terms as scan
from yoke_project_checks._obsoleted_terms_prefilter import (
    _literal_choices,
    _whole_text_gate,
    required_test,
)


def _texts_for(required: re.Pattern) -> list[str]:
    """Texts that do and do not carry the candidate, built from the catalog."""
    texts = ["nothing relevant here\n"]
    for literal in _literal_choices(required) or []:
        texts += [f"x {literal} y\n", f"x {literal.upper()} y\n", literal[:-1]]
    return texts


@pytest.mark.parametrize("source", list(scan.OBSOLETED_TERM_PATTERNS))
def test_presence_check_matches_the_required_regex(source: str) -> None:
    required = scan._required_candidate(re.compile(source))
    present = required_test(required)
    if required is None:
        assert present is None
        return
    for text in _texts_for(required):
        assert bool(present(text)) == bool(required.search(text)), (source, text)


@pytest.mark.parametrize(
    "source",
    [r"^foo", r"foo$", r"(?<!x)foo", r"foo(?=bar)", r"foo(?!bar)", r"\Afoo"],
)
def test_line_context_patterns_keep_the_per_line_scan(source: str) -> None:
    assert _whole_text_gate(source) is None


def test_whole_text_gate_finds_every_line_match() -> None:
    gate = _whole_text_gate(r"\bwidget_rules\b")
    assert gate is not None
    assert gate.search("first\nset widget_rules here\nlast\n")
    assert not gate.search("first\nwidget_rulesx\n")


@pytest.mark.parametrize(
    "source", [r"items[^\n]*WHERE", r"[^^$]+", r"[]^$]+", r"[\]$^]+", r"\^literal\$"]
)
def test_literal_anchor_characters_keep_the_whole_file_gate(source):
    assert _whole_text_gate(source) is not None


@pytest.mark.parametrize(
    "source",
    [
        r"[^x]^foo",
        r"[]^]+$",
        r"[\]](?=foo)",
        r"[x]\Afoo",
        r"(?# [)^foo]",
        r"(?x) foo $ # bar",
    ],
)
def test_line_context_after_a_class_or_comment_keeps_the_line_scan(source):
    assert _whole_text_gate(source) is None


@pytest.mark.parametrize("suffix", [r"\b", ""])
def test_noncapturing_literal_choices_skip_absent_files(suffix):
    source = r"\b(?:retired_key|former_key)" + suffix
    required = scan._required_candidate(re.compile(source))
    assert required is not None
    present = required_test(required)
    assert present("set retired_key here")
    assert present("set former_key_extended here")
    assert not present("set current_key here")


def test_empty_noncapturing_choice_keeps_every_candidate():
    assert scan._required_candidate(re.compile(r"\b(?:retired_key|)\b")) is None


def test_identical_text_reuses_matching_with_distinct_path_exemptions(
    tmp_path, monkeypatch
):
    source = r"\bretired_key\b"
    monkeypatch.setattr(scan, "OBSOLETED_TERM_PATTERNS", (source,))
    monkeypatch.setattr(scan, "OBSOLETED_TERM_LABELS", {source: "key"})
    monkeypatch.setattr(scan, "_PER_PATTERN_PATH_ALLOWLIST", {source: ("docs/exempt",)})
    docs = tmp_path / "docs"
    docs.mkdir()
    for name in ("exempt.md", "a.md", "b.md"):
        (docs / name).write_text("retired_key\n")
    monkeypatch.setattr(
        scan,
        "_iter_scan_paths",
        lambda root: [docs / name for name in ("exempt.md", "a.md", "b.md")],
    )
    calls = []
    original = scan.required_test

    def counted(required):
        test = original(required)

        def run(text):
            calls.append(text)
            return test(text)

        return run

    monkeypatch.setattr(scan, "required_test", counted)
    assert scan.scan_repo(tmp_path) == [
        "docs/a.md:1: [key] retired_key",
        "docs/b.md:1: [key] retired_key",
    ]
    assert calls == ["retired_key\n"]
