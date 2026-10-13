"""Complete verification links retain strict code and entry-path binding."""

import pytest
from subprocess import CompletedProcess

from yoke_contracts.machine_approval_coordinates import machine_approval_coordinates
from yoke_harness import ssh_mac_browser_approval as safari
from yoke_harness.ssh_mac_browser_approval import _approval_tab_urls, _approval_url


@pytest.mark.parametrize("path", ["/connect", "/machine"])
def test_base_and_complete_uris_resolve_to_the_same_exact_request(path):
    base = "https://example.invalid" + path
    complete = base + "?user_code=AB12-CD34"
    assert machine_approval_coordinates(base, "AB12-CD34") == machine_approval_coordinates(
        complete, "AB12-CD34"
    )
    assert _approval_url(complete, "AB12-CD34") == (complete, "https://example.invalid")


def test_self_hosted_code_path_is_preserved_for_the_wizard_opened_tab():
    complete = "https://example.invalid/machine/AB12-CD34"
    assert _approval_url(complete, "AB12-CD34")[0] == complete


@pytest.mark.parametrize("uri", [
    "http://example.invalid/connect",
    "https://user:password@example.invalid/connect",
    "https://example.invalid/anything",
    "https://example.invalid/connect#fragment",
    "https://example.invalid/connect?user_code=EF56-GH78",
    "https://example.invalid/connect?user_code=AB12-CD34&user_code=AB12-CD34",
    "https://example.invalid/connect?other=AB12-CD34",
    "https://example.invalid/connect?user_code=AB12-CD34&other=value",
    "https://example.invalid/connect?user_code",
    "https://example.invalid/machine/EF56-GH78",
])
def test_unrelated_or_ambiguous_coordinates_cannot_be_approved(uri):
    with pytest.raises(ValueError):
        machine_approval_coordinates(uri, "AB12-CD34")


ENTRY = "https://example.invalid/connect?user_code=AB12-CD34"
REDIRECT = "https://example.invalid/orgs/example/machine-approval/AB12-CD34"
DESTINATION = "https://example.invalid/orgs/example/strategy?status=approved"


def test_redirect_keeps_the_exact_origin_code_and_single_organization_segment():
    assert _approval_tab_urls(ENTRY, "AB12-CD34", [REDIRECT, REDIRECT]) == [
        ENTRY, REDIRECT,
    ]


@pytest.mark.parametrize("url", [
    "https://other.invalid/orgs/example/machine-approval/AB12-CD34",
    "http://example.invalid/orgs/example/machine-approval/AB12-CD34",
    "https://user@example.invalid/orgs/example/machine-approval/AB12-CD34",
    "https://example.invalid/orgs/example/machine-approval/EF56-GH78",
    "https://example.invalid/orgs//machine-approval/AB12-CD34",
    "https://example.invalid/orgs/../machine-approval/AB12-CD34",
    "https://example.invalid/orgs/%2e%2e/machine-approval/AB12-CD34",
    "https://example.invalid/orgs/example/other/machine-approval/AB12-CD34",
    REDIRECT + "/",
    REDIRECT + "?user_code=AB12-CD34",
    REDIRECT + "#fragment",
    "https://[invalid",
])
def test_redirect_tab_rejects_ambiguous_or_unrelated_requests(url):
    assert _approval_tab_urls(ENTRY, "AB12-CD34", [url]) == [ENTRY]


def test_machine_entry_does_not_authorize_the_hosted_redirect_route():
    entry = "https://example.invalid/machine/AB12-CD34"
    assert _approval_tab_urls(entry, "AB12-CD34", [REDIRECT]) == [entry]


def _approval(monkeypatch, *, response, observed=REDIRECT, exit_code=0):
    scripts = []
    results = iter([
        CompletedProcess([], 0, observed + "\n", ""),
        CompletedProcess([], exit_code, response, ""),
    ])

    def run_script(_run, script):
        scripts.append(script)
        return next(results)

    monkeypatch.setattr(safari, "run_osascript", run_script)
    outcome = safari.approve_machine_in_safari(
        lambda *_args, **_kwargs: None,
        verification_url=ENTRY,
        user_code="AB12-CD34",
    )
    return outcome, scripts


@pytest.mark.parametrize("starting_url", [ENTRY, REDIRECT])
def test_approval_requires_navigation_from_the_tab_that_was_actually_matched(
    monkeypatch, starting_url,
):
    outcome, scripts = _approval(
        monkeypatch, response=f"approved|{starting_url}|{DESTINATION}",
        observed=starting_url,
    )
    assert outcome.ok
    assert outcome.evidence["approval_entry"] == starting_url.split("?")[0].removeprefix(
        "https://example.invalid"
    )
    assert outcome.evidence["result_url"] == DESTINATION.split("?")[0]
    approval_script = "\n".join(scripts[1])
    assert "set matchedStartingURL to tabURL" in approval_script
    assert "resultURL is not matchedStartingURL" in approval_script
    assert "resultURL is not expectedURL" not in approval_script


@pytest.mark.parametrize("response", [
    f"approved|{REDIRECT}|{REDIRECT}",
    f"approved|{ENTRY}|{ENTRY}",
    f"approved|https://other.invalid/connect|{DESTINATION}",
    f"approved|{REDIRECT.replace('AB12-CD34', 'EF56-GH78')}|{DESTINATION}",
    f"approved|{DESTINATION}",
    "browser_tab_changed",
])
def test_unchanged_redirect_or_unmatched_start_cannot_be_reported_as_approved(
    monkeypatch, response,
):
    outcome, _ = _approval(monkeypatch, response=response)
    assert not outcome.ok


@pytest.mark.parametrize("destination", [
    "https://other.invalid/success",
    "https://example.invalid/connect?status=denied",
    "https://example.invalid/connect?status=expired",
])
def test_clicked_approval_still_rejects_foreign_or_refused_destinations(
    monkeypatch, destination,
):
    outcome, _ = _approval(
        monkeypatch, response=f"approved|{REDIRECT}|{destination}",
    )
    assert outcome.error_code == "machine_browser_approval_destination_invalid"
