"""Subprocess merge clients the import graph cannot reliably follow."""

MERGE_PREFIX_CONTRACTS = (
    (
        "merge_engine_subprocess_contract",
        (
            "packages/yoke-core/src/yoke_core/engines/merge_worktree",
            "packages/yoke-core/src/yoke_core/domain/merge_landing_proof.py",
            "packages/yoke-core/src/yoke_core/domain/standalone_item_merge",
        ),
        (
            "runtime/api/test_merge_worktree_prepare.py",
            "runtime/api/test_merge_worktree_execute.py",
            "runtime/api/test_merge_worktree_post.py",
            "runtime/api/test_merge_worktree_post_diverge.py",
            "runtime/api/test_merge_worktree_additive.py",
            "runtime/api/test_merge_worktree_conflict.py",
            "runtime/api/test_merge_worktree_failfast.py",
            "runtime/api/test_merge_worktree_freshness.py",
            "runtime/api/tools/test_impacted_merge_contracts.py",
        ),
    ),
)
