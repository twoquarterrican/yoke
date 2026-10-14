"""A relay holding a live batch takes newly assigned launches at once."""

from __future__ import annotations

from yoke_contracts.fleet_policy import RELAY_POLL_SECONDS
from yoke_core.domain.session_relay import claim_relay_job
from yoke_core.domain.session_relay_types import RelayHeartbeat
from yoke_core.domain.session_wake_drain_cadence import RELAY_DRAIN_POLL_SECONDS
from runtime.api.domain.session_launch_test_support import (
    NOW,
    add_relay,
    assigned_launch,
    relay_connection,
)


MACHINE_ID = "11111111-1111-4111-8111-111111111111"
RELAY_ID = f"machine:{MACHINE_ID}"
WAIT_SECONDS = 55


def _connection():
    conn = relay_connection()
    add_relay(conn, relay_id=RELAY_ID, machine_id=MACHINE_ID)
    return conn


def _heartbeat() -> RelayHeartbeat:
    return RelayHeartbeat(
        relay_id=RELAY_ID,
        actor_id=1,
        machine_id=MACHINE_ID,
        hostname="relay-host",
        relay_version="0.1.1",
        surface_versions={"codex-cli": "0.148.0a15"},
        project_ids=(10,),
    )


class _FakeClock:
    """Monotonic time that only moves when the long poll sleeps."""

    def __init__(self, on_sleep=None) -> None:
        self.elapsed = 0.0
        self.sleeps = 0
        self._on_sleep = on_sleep

    def monotonic(self) -> float:
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        self.elapsed += seconds
        self.sleeps += 1
        if self._on_sleep is not None:
            self._on_sleep(self.sleeps)


def _long_poll(conn, clock: _FakeClock):
    return claim_relay_job(
        conn,
        _heartbeat(),
        wait_seconds=WAIT_SECONDS,
        now_provider=lambda: NOW,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )


def test_a_poll_that_leased_launches_asks_the_relay_straight_back() -> None:
    conn = _connection()
    assigned_launch(conn, key="first", machine_id=MACHINE_ID)

    outcome = _long_poll(conn, _FakeClock())

    assert [job.job_kind for job in outcome.jobs] == ["launch"]
    assert outcome.next_poll_seconds == RELAY_DRAIN_POLL_SECONDS


def test_a_launch_assigned_during_a_live_batch_is_claimed_within_a_step() -> None:
    conn = _connection()
    assigned_launch(conn, key="first", machine_id=MACHINE_ID)
    _long_poll(conn, _FakeClock())

    def assign_second(sleeps: int) -> None:
        if sleeps == 1:
            assigned_launch(conn, key="second", machine_id=MACHINE_ID)

    clock = _FakeClock(on_sleep=assign_second)
    outcome = _long_poll(conn, clock)

    assert [job.job_kind for job in outcome.jobs] == ["launch"]
    assert clock.elapsed <= RELAY_DRAIN_POLL_SECONDS
    assert outcome.next_poll_seconds == RELAY_DRAIN_POLL_SECONDS


def test_a_live_batch_with_nothing_new_long_polls_then_comes_straight_back() -> None:
    conn = _connection()
    assigned_launch(conn, key="first", machine_id=MACHINE_ID)
    _long_poll(conn, _FakeClock())

    clock = _FakeClock()
    outcome = _long_poll(conn, clock)

    assert outcome.jobs == ()
    assert clock.elapsed == WAIT_SECONDS
    assert outcome.next_poll_seconds == RELAY_DRAIN_POLL_SECONDS


def test_an_idle_relay_still_long_polls_at_the_ordinary_cadence() -> None:
    conn = _connection()

    clock = _FakeClock()
    outcome = _long_poll(conn, clock)

    assert outcome.jobs == ()
    assert clock.elapsed == WAIT_SECONDS
    assert outcome.next_poll_seconds == RELAY_POLL_SECONDS
