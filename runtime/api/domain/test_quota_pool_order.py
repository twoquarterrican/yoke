"""Cursor order precedes headroom without adding other-vendor priorities."""

from dataclasses import replace
import pytest
from yoke_core.domain.quota_pool_order import (
    validate_cursor_quota_order,
    QuotaPoolOrderError,
)
from yoke_core.domain.session_launch_level_candidate import LevelCandidate
from yoke_core.domain.session_launch_level_placement import (
    _choose,
    RULE_SPREAD,
    RULE_HEADROOM,
)

ORDER = ("Cursor Models", "Other Models")


def candidate(model, headroom, *, index=0, surface="cursor-cli", workers=1):
    return LevelCandidate(
        option_index=index,
        surface=surface,
        model=model,
        reasoning_effort="high",
        context_window_tokens=None,
        machine_id="machine",
        headroom_percent=headroom,
        live_workers=workers,
    )


def test_cursor_pool_order_precedes_headroom():
    first = candidate("grok-4.7-high-fast", 1)
    later = candidate("claude-opus-5-5-medium", 900, index=1)
    assert _choose([later, first], ORDER) == (first, RULE_HEADROOM)


def test_reversing_order_changes_consumption_without_a_model_preference():
    chosen, _ = _choose(
        [candidate("grok-4.7-high", 900), candidate("claude-opus-5-5-medium", 1)],
        tuple(reversed(ORDER)),
    )
    assert chosen.model == "claude-opus-5-5-medium"


def test_when_preferred_pool_is_blocked_remaining_pool_can_launch():
    other = candidate("claude-opus-5-5-medium", 20)
    assert _choose([other], ORDER)[0] == other


def test_same_pool_uses_headroom_then_configuration_position():
    normal = candidate("grok-4.7-high", 10, index=0)
    fast = candidate("grok-4.7-high-fast", 20, index=1)
    assert _choose([normal, fast], ORDER) == (fast, RULE_HEADROOM)
    assert _choose([normal, replace(fast, headroom_percent=10)], ORDER)[0] == normal


def test_existing_spread_rule_remains():
    idle = candidate("gpt-6.1-sol", 200, surface="codex-cli", workers=0)
    busy = candidate("claude-opus-5-5", 300, surface="claude-cli", workers=1)
    assert _choose([idle, busy], ORDER) == (idle, RULE_SPREAD)


def test_other_harnesses_still_compete_by_existing_headroom():
    opus = candidate("claude-opus-5-5", 50, surface="claude-cli")
    sonnet = candidate("claude-sonnet-5-5", 5, surface="claude-cli")
    assert _choose([opus, sonnet], ORDER) == (opus, RULE_HEADROOM)


@pytest.mark.parametrize(
    "pools",
    [
        [],
        ["Cursor Models"],
        ["Cursor Models", "Cursor Models"],
        ["Cursor Models", "Other Models", "extra"],
        ["other", "Cursor Models"],
        {"machines": {}},
        [None, {}],
    ],
)
def test_order_requires_exactly_two_monthly_pools(pools):
    with pytest.raises(QuotaPoolOrderError, match="Recovery:"):
        validate_cursor_quota_order(pools)


def test_either_exact_order_is_valid():
    assert validate_cursor_quota_order(list(ORDER)) == ORDER
    assert validate_cursor_quota_order(list(reversed(ORDER))) == tuple(reversed(ORDER))
