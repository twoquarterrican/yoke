"""The public CLI dispatches terminal claim mutations without internal clients."""

from unittest.mock import patch

import pytest

from runtime.api.cli.test_yoke_operations_cli_claims import _CAPTURED, _run


@pytest.mark.parametrize("action", ["release", "cancel"])
def test_terminal_dispatch(action):
    _CAPTURED.clear()
    code, _, _ = _run(
        "claims",
        "path",
        action,
        "--item",
        "EXT-42",
        "--claim-id",
        "17",
        "--reason",
        "coverage finished",
        "--json",
    )
    assert code == 0
    request = _CAPTURED[-1]
    assert request.function == f"claims.path.{action}"
    assert request.target.public_ref == "EXT-42"
    assert request.payload == {"claim_id": 17, "reason": "coverage finished"}


@pytest.mark.parametrize("action", ["release", "cancel"])
def test_reason_and_item_required(action):
    code, _, _ = _run("claims", "path", action, "--claim-id", "17")
    assert code == 2


@pytest.mark.parametrize("action", ["release", "cancel"])
def test_help_teaches_holder_and_fresh_coverage(action):
    with patch("yoke_cli.commands._helpers.ensure_handlers_loaded"):
        code, out, _ = _run("claims", "path", action, "--help")
    assert code == 0
    assert "work claim" in out
    assert "fresh coverage" in out
