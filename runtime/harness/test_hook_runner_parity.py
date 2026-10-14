"""Universal-ordering parity tests + structural reachability backstop.

Every ``(event_name, matcher)`` key in
:data:`yoke_contracts.hook_runner.hook_ordering.HOOK_ORDERING` is
exercised, both for chain equality (claude / codex modulo the runner's
``_apply_omissions`` filter) and for structural reachability (every
chained module id must be either typed-evaluable or an explicit
``subprocess_modules`` carve-out — no third state).

The runner-behavior band (timeout, subprocess carve-out exit-code paths,
dry-run CLI, real-chain ``sqlite3`` denial smoke test) lives in
``test_hook_runner.py`` so the parity surface here can stay narrow. The
chain registry, runner core, and adapter capability tests live in their
own files (``test_hook_runner_chain_registry.py``,
``test_hook_runner_runner.py``, ``test_hook_runner_decision_render.py``).
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from yoke_contracts.hook_runner.chain_registry import chain_for
from yoke_contracts.hook_runner.hook_ordering import HOOK_ORDERING, ordered_pipeline_for
from yoke_core.hooks.claude_adapter import CAPABILITY as CLAUDE_CAPABILITY
from yoke_core.hooks.codex_adapter import CAPABILITY as CODEX_CAPABILITY
from yoke_core.hooks.cursor_adapter import CAPABILITY as CURSOR_CAPABILITY
from yoke_core.hooks import runner as runner_module
from yoke_core.hooks.adapter_capability import AdapterCapability

pytestmark = pytest.mark.usefixtures("bound_project_context")


_CAPABILITIES = (CLAUDE_CAPABILITY, CODEX_CAPABILITY, CURSOR_CAPABILITY)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _runner_filtered_chain(
    event_name: str,
    matcher: str,
    capability: AdapterCapability,
) -> list[str]:
    """Apply the runner's ``_apply_omissions`` exactly as the runner would.

    Coupling the parity test to ``runner_module._apply_omissions`` means
    that if the omission semantics shift (e.g. Codex starts honoring
    ``apply_patch_chain_omissions`` for ``PreToolUse[apply_patch]``
    directly), this helper picks up the change without test edits.
    """
    return runner_module._apply_omissions(
        chain_for(event_name, matcher),
        event_name=event_name,
        capability=capability,
    )


def _all_chain_keys() -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    for event_name, matchers in HOOK_ORDERING.items():
        for matcher in matchers:
            keys.append((event_name, matcher))
    return keys


def _module_ids_in_registry() -> set[str]:
    ids: set[str] = set()
    for matchers in HOOK_ORDERING.values():
        for chain in matchers.values():
            for module_id in chain:
                ids.add(module_id)
    return ids


# ---------------------------------------------------------------------------
# Chain equality across every (event, matcher) for both harnesses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "capability",
    _CAPABILITIES,
    ids=lambda c: c.family,
)
@pytest.mark.parametrize(("event_name", "matcher"), _all_chain_keys())
def test_filtered_chain_matches_universal_ordering(
    event_name: str,
    matcher: str,
    capability: AdapterCapability,
) -> None:
    """Each harness's filtered chain equals the universal-source chain.

    Neither harness declares chain omissions, so the runner's omission
    filter must pass every registry chain through unchanged for both.
    """
    expected = list(ordered_pipeline_for(event_name, matcher))
    actual = _runner_filtered_chain(event_name, matcher, capability)
    assert actual == expected


@pytest.mark.parametrize(
    "capability",
    _CAPABILITIES,
    ids=lambda c: c.family,
)
def test_declared_omissions_name_modules_present_in_their_chain(
    capability: AdapterCapability,
) -> None:
    """Every declared omission must name a module the chain actually contains.

    An omission naming a module absent from the chain filters nothing —
    it silently misdocuments a harness asymmetry that does not exist.
    """
    apply_patch_chain = set(ordered_pipeline_for("PreToolUse", "apply_patch"))
    stray = capability.apply_patch_chain_omissions - apply_patch_chain
    assert stray == set(), (
        f"{capability.family}: apply_patch_chain_omissions names modules "
        f"absent from the apply_patch chain: {sorted(stray)}"
    )
    pretool_modules: set[str] = set()
    for chain in HOOK_ORDERING["PreToolUse"].values():
        pretool_modules.update(chain)
    stray_pre = capability.pretool_omissions - pretool_modules
    assert stray_pre == set(), (
        f"{capability.family}: pretool_omissions names modules absent "
        f"from every PreToolUse chain: {sorted(stray_pre)}"
    )


# ---------------------------------------------------------------------------
# Every chain module is typed-evaluable OR a subprocess carve-out
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_id", sorted(_module_ids_in_registry()))
def test_chain_module_is_typed_or_subprocess_carveout(module_id: str) -> None:
    """Structural backstop preventing the runner-broken failure mode.

    A module that is neither typed-evaluable nor an explicit
    ``subprocess_modules`` carve-out crashes the runner at first dispatch
    with ``failure="missing_evaluate"`` and floods the events table with
    ``HookExecutionFailed``. This test fails closed before that lands.
    """
    in_subprocess_carveout = (
        module_id in CLAUDE_CAPABILITY.subprocess_modules
        or module_id in CODEX_CAPABILITY.subprocess_modules
        or module_id in CURSOR_CAPABILITY.subprocess_modules
    )
    if in_subprocess_carveout:
        return
    module = importlib.import_module(module_id)
    evaluator = getattr(module, "evaluate", None)
    assert callable(evaluator), (
        f"{module_id} is neither in any capability.subprocess_modules nor "
        f"exposes a callable evaluate(); the runner would emit "
        f"HookExecutionFailed{{failure='missing_evaluate'}} on first dispatch."
    )


# ---------------------------------------------------------------------------
# File-line cap (this file <= 350 lines; matches the project hard cap)
# ---------------------------------------------------------------------------


def test_parity_file_under_350_lines() -> None:
    """Parity file at or below the 350-line hard cap."""
    here = Path(__file__).resolve()
    with here.open("rb") as fh:
        line_count = sum(1 for _ in fh)
    assert line_count <= 350, f"{here.name} is {line_count} lines"
