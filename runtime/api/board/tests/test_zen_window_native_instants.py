"""Timeline calendar cutoffs stay equal across native recording and UTC replay."""

from datetime import timedelta, timezone

import pytest

from yoke_contracts.board.data import BOARD_DATA_VERSION, ReplayBoardDB
from yoke_contracts.board import zen_data
from yoke_contracts.timestamps import InvalidInstant, parse_instant
from yoke_core.board.data import RecordingBoardDB


@pytest.mark.parametrize("offset", [-300, 0, 345])
def test_window_uses_utc_day_before_and_after_recording(monkeypatch, offset):
    monkeypatch.setattr(zen_data, "_zen_project_id", lambda db, project: 1)
    stamp = parse_instant("2025-01-01T00:00:00.000001Z").astimezone(
        timezone(timedelta(minutes=offset))
    )

    class DB:
        def scalar(self, sql, params):
            return stamp

    recorder = RecordingBoardDB(DB())
    assert zen_data._zen_compute_window(recorder, "example") == "2025-01-01"
    replay = ReplayBoardDB.from_payload(
        {
            "version": BOARD_DATA_VERSION,
            "entries": recorder.encoded_entries(),
        }
    )
    assert zen_data._zen_compute_window(replay, "example") == "2025-01-01"


@pytest.mark.parametrize("value", [None, "2025-01-01"])
def test_window_has_explicit_absence_and_refuses_ambiguous_clocks(monkeypatch, value):
    monkeypatch.setattr(zen_data, "_zen_project_id", lambda db, project: 1)

    class DB:
        def scalar(self, sql, params):
            return value

    if value is None:
        assert zen_data._zen_compute_window(DB(), "example") is None
    else:
        with pytest.raises(InvalidInstant):
            zen_data._zen_compute_window(DB(), "example")
