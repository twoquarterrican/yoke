"""Complete verification links retain strict code and entry-path binding."""

import pytest

from yoke_contracts.machine_approval_coordinates import machine_approval_coordinates
from yoke_harness.ssh_mac_browser_approval import _approval_url


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
