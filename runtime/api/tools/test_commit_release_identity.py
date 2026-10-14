"""One release identity preserves commit chronology and UTC everywhere."""

from datetime import datetime, timedelta, timezone

from packaging.version import Version
import pytest

from yoke_contracts.release_version import (
    commit_version,
    release_version,
    version_order,
)


def test_commit_clock_uses_utc_and_bumped_base():
    clock = datetime(2026, 10, 13, 20, 13, 59, tzinfo=timezone(timedelta(hours=-4)))
    assert commit_version(clock) == "0.2.0.202610140013"


def test_python_version_is_identical_to_tag_and_display():
    version = "0.2.0.202610140013"
    assert str(Version(version)) == version
    assert release_version(version) == version


def test_public_and_wheel_forms_sort_identically_across_minutes_and_days():
    names = [
        "0.2.0.202610132359",
        "0.2.0.202610140000",
        "0.2.0.202610140013",
        "0.2.0.202610140100",
        "0.3.0.202601010000",
    ]
    assert sorted(reversed(names), key=version_order) == names
    assert sorted(reversed(names), key=Version) == names


@pytest.mark.parametrize(
    "value",
    [
        "0.2.0.202602300013",
        "0.2.0.202610142400",
        "0.2.0.20261014013",
        "v0.2.0.202610140013",
    ],
)
def test_invalid_or_aliased_release_names_refuse(value):
    with pytest.raises(ValueError):
        release_version(value)
