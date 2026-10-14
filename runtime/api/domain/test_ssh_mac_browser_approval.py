"""Native Safari approval is exact-target, visible-control automation."""

from __future__ import annotations

import subprocess

import pytest

from yoke_core.domain.ssh_mac_browser_approval import approve_machine_in_safari

ENTRY_URL = "https://app.stage.upyoke.com/connect?user_code=AB12-CD34"
REDIRECT_URL = "https://app.stage.upyoke.com/orgs/acme/machine-approval/AB12-CD34"


def _completed(
    command: str,
    *,
    stdout: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout, "")


@pytest.mark.parametrize("starting_url", [ENTRY_URL, REDIRECT_URL])
def test_approval_targets_the_exact_code_tab_and_visible_button(starting_url) -> None:
    commands: list[str] = []

    def run(command: str, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return _completed(
            command,
            stdout=(
                starting_url + "\n" if "return tabURLs" in command
                else f"approved|{starting_url}|https://app.stage.upyoke.com/orgs/acme/frontier\n"
            ),
        )

    result = approve_machine_in_safari(
        run,
        verification_url="https://app.stage.upyoke.com/connect",
        user_code="AB12-CD34",
    )

    assert result.ok is True
    assert result.error_code is None
    assert result.evidence == {
        "approval_entry": starting_url.removeprefix("https://app.stage.upyoke.com").split("?")[0],
        "browser": "Safari",
        "result_url": "https://app.stage.upyoke.com/orgs/acme/frontier",
        "visible_control": "Approve machine",
    }
    assert len(commands) == 2
    assert ENTRY_URL in commands[1]
    assert starting_url in commands[1]
    assert "Approve machine" in commands[1]
    assert 'perform action "AXPress"' in commands[1]
    assert 'resultURL is not matchedStartingURL' in commands[1]
    assert 'return "approved|" & matchedStartingURL & "|" & resultURL' in commands[1]


@pytest.mark.parametrize(
    ("verification_url", "user_code"),
    (
        ("http://app.stage.upyoke.com/connect", "AB12-CD34"),
        ("https://app.stage.upyoke.com/anything", "AB12-CD34"),
        ("https://app.stage.upyoke.com/connect?other=1", "AB12-CD34"),
        ("https://app.stage.upyoke.com/connect", "bad-code"),
    ),
)
def test_invalid_context_never_reaches_safari(
    verification_url: str,
    user_code: str,
) -> None:
    commands: list[str] = []

    result = approve_machine_in_safari(
        lambda command, **_kwargs: commands.append(command) or _completed(command),
        verification_url=verification_url,
        user_code=user_code,
    )

    assert result.ok is False
    assert result.error_code == "machine_browser_context_invalid"
    assert commands == []


@pytest.mark.parametrize(
    ("stdout", "error_code"),
    (
        ("browser_tab_missing\n", "machine_browser_tab_missing"),
        (
            "approval_control_missing\n",
            "machine_browser_approval_control_missing",
        ),
        (
            "approval_navigation_missing\n",
            "machine_browser_approval_navigation_missing",
        ),
        (
            f"approved|{ENTRY_URL}|https://evil.example/orgs/acme\n",
            "machine_browser_approval_destination_invalid",
        ),
        (
            f"approved|{ENTRY_URL}|https://app.stage.upyoke.com/connect?status=denied\n",
            "machine_browser_approval_destination_invalid",
        ),
    ),
)
def test_automation_refuses_missing_or_untrusted_browser_outcomes(
    stdout: str,
    error_code: str,
) -> None:
    result = approve_machine_in_safari(
        lambda command, **_kwargs: _completed(
            command, stdout=ENTRY_URL + "\n" if "return tabURLs" in command else stdout,
        ),
        verification_url="https://app.stage.upyoke.com/connect",
        user_code="AB12-CD34",
    )

    assert result.ok is False
    assert result.error_code == error_code
