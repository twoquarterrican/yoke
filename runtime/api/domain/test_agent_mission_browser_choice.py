"""Mission walkers pick a browser that exists on the Test Machine."""

from __future__ import annotations

import pytest

from yoke_core.domain.agent_mission_review import agent_mission_dispatch_contract


EXECUTION_ID = "01JQ8P4Z9K2M7V6T5R3N1B0AXY"


def _walker(executor: str, identities: list[str] | None = None) -> dict:
    bundle = {
        "bundle_id": "bundle-1",
        "bundle_digest": "d" * 64,
        "execution_id": EXECUTION_ID,
        "subject": {"item_id": 4550, "deployment_run_id": None},
        "execution_target": {
            "project": {"id": 1, "slug": "yoke"},
            "environment": {"name": "stage"},
            "tenant": {"slug": "yoke"},
            "endpoints": {"base_url": "https://stage.example"},
        },
        "execution_target_digest": "e" * 64,
        "cases": [
            {
                "requirement_id": 18152,
                "capture_runner": "agent_mission",
                "capture_run_id": 991,
                "executor": executor,
                "method_config": {"browser_identities": identities or []},
                "instructions": "Install as a new user.",
                "expected_outcome": "Ranked findings.",
                "artifacts": [],
                "transcript": {},
            }
        ],
    }
    return agent_mission_dispatch_contract(bundle)["walker_dispatches"][0]


@pytest.mark.parametrize("executor", ["naive_target_session", "informed_subagent"])
def test_walker_prompt_uses_yoke_browser_only_when_the_walk_installed_yoke(
    executor: str,
) -> None:
    walker = _walker(executor)
    prompt = walker["prompt"]

    assert "if Yoke is on the target because this walk installed it" in prompt
    assert walker["browser_setup_command"] in prompt
    assert walker["browser_step_command"] in prompt
    assert "Otherwise open the host's own browser" in prompt
    assert "Safari on macOS" in prompt
    assert "the desktop's default browser elsewhere" in prompt
    assert "screenshots and keystrokes" in prompt
    assert "Never install Yoke on a Test Machine to get a browser." in prompt


@pytest.mark.parametrize("executor", ["naive_target_session", "informed_subagent"])
@pytest.mark.parametrize("identities", [["operator"], ["operator", "admin"]])
def test_named_identities_select_managed_browser_without_installing_yoke(
    executor: str, identities: list[str]
) -> None:
    walker = _walker(executor, identities)
    prompt = walker["prompt"]

    assert "For named browser identities, use the managed browser" in prompt
    assert "because this walk installed it" not in prompt
    assert "Otherwise open the host's own browser" not in prompt
    assert walker["browser_setup_command"] in prompt
    assert walker["browser_step_command"] in prompt
    assert walker["browser_identities"] == identities
    for name, command in zip(identities, walker["browser_verify_commands"]):
        assert f"--identity {name}" in command
        assert command in prompt
    assert "pass `--identity NAME` to every step" in prompt
    assert "HUMAN_GATE naming the identity, the site and the account" in prompt
    assert "Never install Yoke on a Test Machine to get a browser." in prompt
