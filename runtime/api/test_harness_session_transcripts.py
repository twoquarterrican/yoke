"""Each harness manifest names its local transcript store from one contract."""

from __future__ import annotations

import json

import pytest

from runtime.api.skill_doc_regressions_test_helpers import REPO
from yoke_contracts.harness_session_transcripts import (
    HARNESS_SESSION_TRANSCRIPTS,
    session_transcripts_for_harness,
)

MANIFEST_DIRS = {"claude-code": "claude", "codex": "codex", "cursor": "cursor"}


@pytest.mark.parametrize("harness_id", sorted(MANIFEST_DIRS))
def test_rendered_manifest_carries_the_contract_entry(harness_id):
    manifest = json.loads(
        (
            REPO / "runtime" / "harness" / MANIFEST_DIRS[harness_id] / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    rendered = manifest["session_transcripts"]
    expected = HARNESS_SESSION_TRANSCRIPTS[harness_id].to_json()
    assert {key: rendered[key] for key in expected} == expected
    assert rendered["store"] == "local_jsonl"
    assert rendered["location"].startswith("~/")
    assert rendered["project_match"]


def test_unknown_harness_names_no_location():
    entry = session_transcripts_for_harness("not-a-harness")
    assert entry.store == "unverified"
    assert entry.location == ""
    assert "HARNESS_SESSION_TRANSCRIPTS" in entry.evidence
