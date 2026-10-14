"""Approve one exact machine request through a visible Safari tab."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit

from yoke_contracts.machine_approval_coordinates import machine_approval_coordinates

from yoke_harness.ssh_mac_terminal_app import RunRemote, run_osascript


_RESULT_SEPARATOR = "|"
_REFUSED_STATUSES = frozenset(
    {"denied", "expired", "missing", "not_admin", "not_member", "used"}
)


@dataclass(frozen=True)
class BrowserApprovalResult:
    """Bounded result of one native browser approval attempt."""

    ok: bool
    evidence: dict[str, Any]
    error_code: str | None = None


def _approval_url(verification_url: str, user_code: str) -> tuple[str, str]:
    coordinates = machine_approval_coordinates(verification_url, user_code)
    return coordinates.complete_uri, coordinates.origin


def _approval_tab_urls(expected_url: str, user_code: str, observed: list[str]) -> list[str]:
    """Allow the entry URL or its same-origin, exact-code organization route."""
    expected = urlsplit(expected_url)
    allowed = [expected_url]
    if expected.path != "/connect":
        return allowed
    for value in observed:
        try:
            parsed = urlsplit(value)
        except ValueError:
            continue
        parts = parsed.path.split("/")
        if (
            parsed.scheme == expected.scheme
            and parsed.netloc == expected.netloc
            and not parsed.query
            and not parsed.fragment
            and len(parts) == 5
            and parts[1] == "orgs"
            and parts[2] not in ("", ".", "..")
            and "%" not in parts[2]
            and parts[3:] == ["machine-approval", user_code]
            and value not in allowed
        ):
            allowed.append(value)
    return allowed


def _script(*, allowed_urls: list[str]) -> list[str]:
    allowed = "{" + ", ".join(json.dumps(url) for url in allowed_urls) + "}"
    label = json.dumps("Approve machine")
    return [
        f"set allowedURLs to {allowed}",
        f"set buttonLabel to {label}",
        "set matchedWindow to missing value",
        "set matchedTab to missing value",
        'tell application "Safari"',
        "repeat with browserWindow in windows",
        "repeat with browserTab in tabs of browserWindow",
        "set tabURL to URL of browserTab as text",
        "if tabURL is in allowedURLs then",
        "set current tab of browserWindow to browserTab",
        "set index of browserWindow to 1",
        "set matchedWindow to browserWindow",
        "set matchedTab to browserTab",
        "set matchedStartingURL to tabURL",
        "exit repeat",
        "end if",
        "end repeat",
        "if matchedWindow is not missing value then exit repeat",
        "end repeat",
        'if matchedWindow is missing value then return "browser_tab_missing"',
        "activate",
        'if (URL of matchedTab as text) is not matchedStartingURL then return "browser_tab_changed"',
        "end tell",
        "delay 0.2",
        "set pressedApproval to false",
        'tell application "System Events"',
        'tell process "Safari"',
        "set frontmost to true",
        "repeat 20 times",
        "try",
        "set allElements to entire contents of front window",
        "repeat with candidate in allElements",
        "try",
        'if (role of candidate as text) is "AXButton" and '
        "(name of candidate as text) is buttonLabel then",
        'perform action "AXPress" of candidate',
        "set pressedApproval to true",
        "exit repeat",
        "end if",
        "end try",
        "end repeat",
        "end try",
        "if pressedApproval then exit repeat",
        "delay 0.25",
        "end repeat",
        "end tell",
        "end tell",
        'if not pressedApproval then return "approval_control_missing"',
        'tell application "Safari"',
        "repeat 40 times",
        "delay 0.25",
        "try",
        "set resultURL to URL of matchedTab as text",
        'if resultURL is not matchedStartingURL then return "approved|" & matchedStartingURL & "|" & resultURL',
        "end try",
        "end repeat",
        "end tell",
        'return "approval_navigation_missing"',
    ]


def _result_url(value: str, *, expected_origin: str) -> str | None:
    parsed = urlsplit(value)
    if f"{parsed.scheme}://{parsed.netloc}" != expected_origin:
        return None
    status = parse_qs(parsed.query).get("status", [""])[0]
    if status in _REFUSED_STATUSES:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def approve_machine_in_safari(
    run: RunRemote,
    *,
    verification_url: str,
    user_code: str,
) -> BrowserApprovalResult:
    """Press the approval button only in the exact wizard-opened Safari tab."""
    try:
        expected_url, expected_origin = _approval_url(verification_url, user_code)
    except ValueError:
        return BrowserApprovalResult(False, {}, "machine_browser_context_invalid")
    tabs = run_osascript(run, [
        'tell application "Safari"',
        'set tabURLs to ""',
        "repeat with browserWindow in windows",
        "repeat with browserTab in tabs of browserWindow",
        "set tabURLs to tabURLs & (URL of browserTab as text) & linefeed",
        "end repeat",
        "end repeat",
        "return tabURLs",
        "end tell",
    ])
    if tabs.returncode:
        return BrowserApprovalResult(
            False, {"browser": "Safari"}, "machine_browser_automation_unavailable"
        )
    allowed_urls = _approval_tab_urls(expected_url, user_code, tabs.stdout.splitlines())
    result = run_osascript(run, _script(allowed_urls=allowed_urls))
    if result.returncode:
        return BrowserApprovalResult(
            False,
            {"browser": "Safari"},
            "machine_browser_automation_unavailable",
        )
    state, separator, navigation = result.stdout.strip().partition(_RESULT_SEPARATOR)
    starting_url, navigation_separator, raw_url = navigation.partition(_RESULT_SEPARATOR)
    errors = {
        "browser_tab_missing": "machine_browser_tab_missing",
        "browser_tab_changed": "machine_browser_tab_changed",
        "approval_control_missing": "machine_browser_approval_control_missing",
        "approval_navigation_missing": "machine_browser_approval_navigation_missing",
    }
    if state != "approved" or not separator:
        return BrowserApprovalResult(
            False,
            {"browser": "Safari", "state": state or "empty"},
            errors.get(state, "machine_browser_approval_failed"),
        )
    if (
        not navigation_separator
        or starting_url not in allowed_urls
        or raw_url == starting_url
    ):
        return BrowserApprovalResult(
            False, {"browser": "Safari"}, "machine_browser_approval_navigation_missing"
        )
    safe_url = _result_url(raw_url, expected_origin=expected_origin)
    if safe_url is None:
        return BrowserApprovalResult(
            False,
            {"browser": "Safari"},
            "machine_browser_approval_destination_invalid",
        )
    return BrowserApprovalResult(
        True,
        {
            "browser": "Safari",
            "approval_entry": urlsplit(starting_url).path,
            "result_url": safe_url,
            "visible_control": "Approve machine",
        },
    )


__all__ = ["BrowserApprovalResult", "approve_machine_in_safari"]
