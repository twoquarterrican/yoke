"""CI timing refresh is complete, scaled, duplicate-free, and atomic."""

import json
from pathlib import Path

import pytest

from yoke_core.tools import ci_durations_refresh as refresh


def _report(root: Path, filename, *, name="test_case", failures=0):
    report = root / filename
    report.write_text(
        f'<testsuites><testsuite time="10" failures="{failures}" errors="0">'
        f'<testcase classname="tests.test_example.Checks" name="{name}" time="20"/>'
        "</testsuite></testsuites>"
    )
    return report


def _root(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_example.py").touch()
    (tmp_path / ".test_durations").write_text('{"prior": 1}')
    return tmp_path


def test_refresh_scales_times_to_actual_shard_walls(tmp_path):
    root = _root(tmp_path)
    result = refresh.refresh(root, [_report(root, "report.xml")], expected_shards=1)
    assert result["profiled_tests"] == 1
    assert json.loads((root / ".test_durations").read_text()) == {
        "tests/test_example.py::Checks::test_case": 10,
    }


def test_refresh_damps_fixture_attribution_noise_and_drops_deleted_tests(tmp_path):
    root = _root(tmp_path)
    key = "tests/test_example.py::Checks::test_case"
    (root / ".test_durations").write_text(json.dumps({key: 2, "deleted": 50}))
    refresh.refresh(root, [_report(root, "report.xml")], expected_shards=1)
    assert json.loads((root / ".test_durations").read_text()) == {key: 6}


def test_changed_fixture_costs_can_replace_prior_weights(tmp_path):
    root = _root(tmp_path)
    key = "tests/test_example.py::Checks::test_case"
    (root / ".test_durations").write_text(json.dumps({key: 90}))
    refresh.refresh(root, [_report(root, "report.xml")], expected_shards=1, reset=True)
    assert json.loads((root / ".test_durations").read_text()) == {key: 10}


@pytest.mark.parametrize("problem", ["missing", "duplicate", "failure"])
def test_bad_report_sets_preserve_prior_profile(tmp_path, problem):
    root = _root(tmp_path)
    report = _report(root, "report.xml", failures=int(problem == "failure"))
    reports = [] if problem == "missing" else [report, report]
    with pytest.raises(ValueError, match="ci_profile_"):
        refresh.refresh(root, reports, expected_shards=2)
    assert (root / ".test_durations").read_text() == '{"prior": 1}'
