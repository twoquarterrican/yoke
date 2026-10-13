"""The isolated welcome probe accepts only its diagnosed write refusal."""

from subprocess import CompletedProcess

import pytest

from runtime.api.domain.test_qa_release_channel_target import _target
from yoke_core.domain.installer_campaign_execution_target import (
    installer_campaign_cases_for_target,
)
from yoke_core.domain.ssh_mac_terminal_recipe_support import run_command_recipe


def _welcome():
    return next(
        case
        for case in installer_campaign_cases_for_target(_target("prod"))
        if case["case_key"] == "welcome-frame"
    )


def _run(text, code):
    case = _welcome()
    return run_command_recipe(
        lambda command, **kwargs: CompletedProcess(command, code, text, ""),
        entry_surface=case["entry_surface"],
        config=case["method_config"],
        staged=[],
        secret_values=[],
    )


def test_read_only_home_refusal_proves_welcome_and_recovery():
    text = (
        "Your operating system for software delivery\nInstalling uv\n"
        "mkdir: /var/empty/.local: Operation not permitted\n"
        "uv installation failed. Install uv manually with the shown command, "
        "then rerun: curl -fsSL https://upyoke.com/install | sh\n"
    )
    result = _run(text, 1)
    assert result.ok
    assert result.evidence["assertion_failures"] == []


@pytest.mark.parametrize("code", [0, 2, 127])
def test_other_exit_codes_do_not_pass_the_refusal_probe(code):
    text = "\n".join(_welcome()["method_config"]["expected_text"])
    result = _run(text, code)
    assert not result.ok
    assert result.error_code == "terminal_recipe_assertion_failed"


def test_unrelated_download_failure_does_not_pass_with_exit_one():
    result = _run(
        "Your operating system for software delivery\nInstalling uv\n"
        "curl: Could not resolve host\n",
        1,
    )
    assert not result.ok
    assert result.evidence["assertion_failures"]
