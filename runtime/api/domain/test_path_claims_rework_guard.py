"""All harnesses share the same fresh-coverage refusal for Bash and edits."""

from unittest.mock import patch

import pytest

from yoke_core.domain.path_claim_bash_guard import evaluate_payload as bash
from yoke_core.domain.path_claim_pre_edit_guard import evaluate_payload as edit
from yoke_core.domain.path_claims_rework_guard import REWORK_COVERAGE_REQUIRED
from yoke_core.domain.observe_normalization import TOOL_KIND_EDIT, ToolEventRecord


@pytest.mark.parametrize("surface", ["bash", "edit"])
def test_rework_refuses_until_fresh_coverage(surface, tmp_path):
    lane = tmp_path / "lane"
    lane.mkdir()
    target = lane / "component.py"
    claim = {
        "state": REWORK_COVERAGE_REQUIRED,
        "public_ref": "EXT-42",
        "owner_item_id": 42,
        "covered_paths": [],
        "worktree_path": str(lane),
        "project_repo_path": str(tmp_path),
    }
    if surface == "bash":
        with patch(
            "yoke_core.domain.path_claim_bash_guard.drop_planning_scratch_mutations",
            side_effect=lambda values, **_: values,
        ):
            result = bash(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "touch component.py"},
                    "cwd": str(lane),
                    "session_id": "holder",
                },
                claim=claim,
            )
    else:
        result = edit(
            ToolEventRecord(
                tool_kind=TOOL_KIND_EDIT,
                tool_name="Edit",
                changed_paths=[str(target)],
                cwd=str(lane),
                session_id="holder",
            ),
            claim=claim,
        )
    assert result.outcome == "deny"
    assert result.failure_mode == REWORK_COVERAGE_REQUIRED
    assert "yoke claims path register --item EXT-42" in result.narrative
    assert "cannot be widened" in result.narrative
