"""Onboarding scans existing work, scopes setup to the first work, hands off."""

from __future__ import annotations

from runtime.api.skill_doc_regressions_test_helpers import SKILLS, _read

ONBOARD_DIR = SKILLS / "onboard"


def test_strategy_step_confirms_the_scan_before_drafting():
    text = _read(ONBOARD_DIR / "strategy-conversation.md")
    assert text.index("## Confirm what to scan") < text.index("## Draft, then decide")
    assert "gh issue list --state open" in text
    assert "gh pr list --state open" in text
    # Transcript stores are harness manifest facts, never restated paths.
    assert "`session_transcripts`" in text and "project_match" in text
    assert "~/.claude" not in text and "~/.codex" not in text
    assert "what else to include" in text
    assert "one at a time" in text and "recommendation" in text
    assert "first work: {outcome}" in text


def test_setup_steps_defer_what_the_first_work_does_not_need():
    router = _read(ONBOARD_DIR / "SKILL.md")
    assert "Steps 2–7 run only when the first work needs them" in router
    assert "never switches projects" in router and "`yoke-global`" in router
    pacing = _read(ONBOARD_DIR / "run-and-rows.md")
    for deferred in ("test registration", "Doctor", "previews", "QA plans"):
        assert deferred in pacing
    assert "scaffold-install=deferred naming the first work" in _read(
        ONBOARD_DIR / "profile-and-scaffold.md"
    )


def test_handoff_routes_filing_through_steering():
    text = _read(ONBOARD_DIR / "first-work.md")
    assert "Onboarding does not file items" in text
    assert "/yoke steer CURRENT-PLAN" in text
    assert "yoke items create" not in text
    assert "yoke qa item-plan attach --item {ITEM}" in text
    assert "installer-campaign plan" in text
    assert "work-seeding=configured" in text
    # Activation is observed, never written.
    assert "--row-status lifecycle-readiness" not in text
    assert "first_item_not_done" in text
