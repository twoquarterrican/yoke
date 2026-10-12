"""Bounded selection keeps subprocess merge behavior on its contract floor."""

from pathlib import Path

import pytest

from yoke_core.tools import impacted_tests
from yoke_core.tools.impacted_tests import build_import_index, select


@pytest.mark.parametrize(
    "source",
    [
        "packages/yoke-core/src/yoke_core/engines/merge_worktree_cleanup.py",
        "packages/yoke-core/src/yoke_core/engines/merge_worktree_prepare.py",
        "packages/yoke-core/src/yoke_core/domain/merge_landing_proof.py",
        "packages/yoke-core/src/yoke_core/domain/standalone_item_merge_post_push.py",
    ],
)
def test_merge_subprocess_clients_survive_bounded_tooling_deferral(
    tmp_path: Path, source: str
) -> None:
    tooling = "packages/yoke-core/src/yoke_core/tools/impacted_tests.py"
    consumers = {
        "runtime/api/test_merge_worktree_prepare.py",
        "runtime/api/test_merge_worktree_execute.py",
        "runtime/api/test_merge_worktree_post.py",
        "runtime/api/test_merge_worktree_post_diverge.py",
    }
    for relative in {source, tooling, *consumers, *impacted_tests.ALWAYS_RUN_TESTS}:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("VALUE = 1\n", encoding="utf-8")
    selected = select([source, tooling], build_import_index(tmp_path), bounded=True)
    assert selected.bounded_deferral
    assert consumers <= set(selected.files)
    assert f"merge_engine_subprocess_contract:{source}" in selected.widening_triggers
