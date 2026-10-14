"""Level placement splits a pool's headroom among the workers already on it."""

from __future__ import annotations

from collections import Counter

import pytest

from yoke_contracts.timestamps import parse_instant
from yoke_core.domain import session_launch_level_placement as placement_module
from yoke_core.domain.session_launch_eligibility import derive_launch_eligibility
from yoke_core.domain.session_launch_level_placement import RULE_HEADROOM, place_level

from runtime.api.domain.session_launch_level_test_support import (
    CLAUDE_OPUS,
    CODEX_SOL,
    CURSOR_OPUS as OPUS_MEDIUM,
    add_surface,
    level_connection,
    pin_live_workers,
    weekly,
    window,
)
from runtime.api.domain.session_launch_test_support import NOW, authorization

#: 30% of the rolling 5h window left, resetting in 93 minutes: about 97%
#: headroom for one worker, the reading that piled a burst onto Claude.
CLAUDE_5H_RESET = "2026-08-22T13:33:00.000000Z"
#: 73% of a monthly pool left with 29.5 days to reset: about 74% headroom.
CURSOR_LATE_MONTH_RESET = "2026-09-21T00:00:00.000000Z"
CLAUDE = ("m-claude", "claude-cli", "claude-opus-5-5")


def _place(conn):
    return place_level(
        conn,
        auth=authorization(actor_id=1),
        project_id=10,
        level="SENIOR",
        machine_id=None,
        now=parse_instant(NOW),
        eligibility=derive_launch_eligibility,
    )


def _claude_near_its_5h_wall(conn) -> None:
    add_surface(
        conn,
        "m-claude",
        "claude-cli",
        [window("rolling_5h", 30.0, resets_at=CLAUDE_5H_RESET)],
    )


def _cursor_other_models(conn) -> None:
    add_surface(
        conn,
        "m-cursor",
        "cursor-cli",
        [
            window(
                "monthly",
                73.0,
                scope="Other Models",
                resets_at=CURSOR_LATE_MONTH_RESET,
            )
        ],
    )


def test_a_crowded_claude_pool_loses_to_an_idle_cursor_pool(monkeypatch) -> None:
    conn = level_connection(OPUS_MEDIUM)
    _claude_near_its_5h_wall(conn)
    _cursor_other_models(conn)
    pin_live_workers(monkeypatch, {CLAUDE: 39})

    placement = _place(conn)

    claude = next(c for c in placement.candidates if c.surface == "claude-cli")
    pool = claude.pools[0]
    assert pool.headroom_percent == pytest.approx(96.77, abs=0.01)
    assert (pool.workers, claude.live_workers) == (39, 39)
    assert claude.headroom_percent == pytest.approx(pool.headroom_percent / 40)
    assert pool.to_dict()["share_percent"] == pytest.approx(claude.headroom_percent)
    assert placement.rule == RULE_HEADROOM
    assert placement.chosen.surface == "cursor-cli"
    assert placement.chosen.headroom_percent == pytest.approx(74.24, abs=0.01)
    assert placement.reason.startswith("most headroom per worker: cursor-cli")


def test_the_reason_names_how_many_ways_the_pool_is_split(monkeypatch) -> None:
    conn = level_connection(CLAUDE_OPUS, CODEX_SOL)
    add_surface(conn, "m-claude", "claude-cli", [weekly(90.0)])
    add_surface(conn, "m-codex", "codex-cli", [weekly(10.0)])
    pin_live_workers(monkeypatch, {CLAUDE: 2})

    placement = _place(conn)

    assert placement.chosen.surface == "claude-cli"
    assert "(weekly · all models, split 3 ways)" in placement.reason


def test_workers_share_only_the_pools_their_model_and_machine_draw_on(
    monkeypatch,
) -> None:
    conn = level_connection(CLAUDE_OPUS)
    add_surface(
        conn, "m-claude", "claude-cli", [weekly(50.0), weekly(40.0, scope="Opus")]
    )
    pin_live_workers(
        monkeypatch,
        {
            ("m-claude", "claude-cli", "claude-fable-5-1"): 3,
            ("m-other", "claude-cli", "claude-opus-5-5"): 5,
            CLAUDE: 1,
        },
    )

    placement = _place(conn)

    pools = {pool.window: pool for pool in placement.chosen.pools}
    # Fable bills the account-wide window but not Opus's own; the other
    # machine's workers draw on that machine's meters.
    assert pools["weekly · all models"].workers == 4
    assert pools["weekly · Opus"].workers == 1
    assert placement.chosen.headroom_window == "weekly · all models"
    assert placement.chosen.headroom_percent == pytest.approx(20.0)


def test_a_burst_of_launches_spreads_across_pools(monkeypatch) -> None:
    conn = level_connection(OPUS_MEDIUM, CODEX_SOL)
    _claude_near_its_5h_wall(conn)
    _cursor_other_models(conn)
    add_surface(conn, "m-codex", "codex-cli", [weekly(30.0)])
    in_flight: Counter = Counter()
    monkeypatch.setattr(placement_module, "live_workers", lambda _conn: in_flight)

    placed = []
    for _ in range(6):
        chosen = _place(conn).chosen
        in_flight[(chosen.machine_id, chosen.surface, chosen.model)] += 1
        placed.append(chosen.surface)

    assert placed == [
        "claude-cli",
        "cursor-cli",
        "codex-cli",
        "claude-cli",
        "cursor-cli",
        "claude-cli",
    ]
