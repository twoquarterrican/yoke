"""Unknown sealed probe exits get one retry without hiding the first failure."""

from types import SimpleNamespace

import pytest

from yoke_harness.ssh_mac_baseline_probes import BaselineProbe, run_baseline_probes


@pytest.mark.parametrize("gui", [True, False])
@pytest.mark.parametrize("second_code", [0, 1, 13])
def test_undeclared_exit_retries_once_and_keeps_both_attempts(gui, second_code):
    calls = []
    codes = iter([1, second_code])

    def run(argv, timeout):
        calls.append((argv, timeout))
        return SimpleNamespace(returncode=next(codes), stdout="private", stderr="")

    result = run_baseline_probes(
        [
            BaselineProbe(
                "Cursor real request", ("/usr/bin/python3", "-c", "probe"), None
            )
        ],
        run_gui_command=run,
        classify_gui_failures=gui,
    )

    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert result.ok is (second_code == 0)
    rows = result.evidence["probes"]
    assert len(rows) == 2
    assert rows[0]["outcome"] == "retrying"
    assert rows[0]["cause"] == "probe_exit_undeclared"
    assert rows[0]["attempt"] == 1
    assert rows[1]["exit_code"] == second_code
    assert rows[1]["outcome"] == ("passed" if second_code == 0 else "failed")
    assert "private" not in repr(result.evidence)
    if second_code:
        assert result.error_code == "baseline_probe_failed"


@pytest.mark.parametrize("code", [10, 11, 12, 13, 14, 15])
def test_declared_standard_cause_never_retries(code):
    calls = []

    def run(argv, timeout):
        calls.append(argv)
        return SimpleNamespace(returncode=code, stdout="", stderr="")

    result = run_baseline_probes(
        [
            BaselineProbe(
                "Claude real request", ("/usr/bin/python3", "-c", "probe"), None
            )
        ],
        run_gui_command=run,
    )

    assert not result.ok
    assert result.error_code == "baseline_probe_failed"
    assert len(calls) == 1
    assert len(result.evidence["probes"]) == 1


def test_explicit_signed_out_harness_refusal_never_retries():
    calls = []

    def run(argv, timeout):
        calls.append(argv)
        return SimpleNamespace(returncode=1, stdout="", stderr="Not logged in")

    result = run_baseline_probes(
        [BaselineProbe("Claude", ("/usr/bin/claude", "auth", "status"), None)],
        run_gui_command=run,
    )

    assert not result.ok
    assert result.evidence["probes"][0]["cause"] == "probe_harness_exit_nonzero"
    assert len(calls) == 1
