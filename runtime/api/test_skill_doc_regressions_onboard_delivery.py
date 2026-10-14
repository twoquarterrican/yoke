"""Onboard scopes setup and delivery to the first work, then hands it off."""

from runtime.api.skill_doc_regressions_test_helpers import _read

from runtime.api.test_skill_doc_regressions_onboard import ONBOARD_DIR, _onboard_bundle


def test_onboard_validates_serving_runtime_before_enabling_a_flow() -> None:
    text = " ".join(_onboard_bundle().split())
    assert "yoke deployment-flows validate --project {project}" in text
    assert "execution_supported=false" in text
    assert "create disabled, never assign default/advanced preview" in text
    assert (
        "yoke workflows delivery-default set --project {project} --workflow dash"
        in text
    )
    assert "never --apply-to-all" in text
    assert "Task exempt" in text
    assert "yoke workflows mechanics get --json" in text
    assert (
        "Actual non-web/non-Yoke targets need no invented stage/preview environment"
        in text
    )
    assert "ephemeral-env" in text
    for workflow in ("dash", "issue", "epic", "blitz"):
        assert (
            f"yoke workflows delivery-default set --project {{project}} "
            f"--workflow {workflow} --flow {{project}}-merge-only"
        ) in text
    assert "all four workflow defaults, which override project default" in text
    # A merge-only default delivers; it does not exempt the item from the
    # stages its pinned definition declares on the way to done.
    assert "discharges delivery at merge" in text
    assert "no deployment run" in text


def test_onboard_profile_keeps_task_exempt_and_preview_guarded() -> None:
    text = _read(ONBOARD_DIR / "profile-and-scaffold.md")
    assert "hosting-and-environments.md" in text
    owner = _read(ONBOARD_DIR / "hosting-and-environments.md")
    assert "yoke workflows delivery-default set" in owner
    assert "Task exempt: never --apply-to-all" in owner
    assert "execution_supported=true" in text


def test_strategy_step_confirms_the_scan_before_drafting():
    text = _read(ONBOARD_DIR / "strategy-conversation.md")
    assert text.index("## Confirm what to scan") < text.index("## Draft, then decide")
    assert "yoke github open-work list --project {project} --json" in text
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
