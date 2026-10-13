"""Doctor adapter for the shared Python and native-driver deadline owner."""

from __future__ import annotations

import time
from yoke_contracts.doctor_budget import (
    CHECK_BUDGET_S,
    DoctorBudgetExhausted,
    remaining_seconds,
)
from yoke_core.domain.python_execution_deadline import native_call, run_bounded


def driver_call(method, *args, **kwargs):
    try:
        return native_call(method, *args, **kwargs)
    except Exception as exc:
        if getattr(exc, "sqlstate", None) == "57014":
            raise DoctorBudgetExhausted("doctor_check_budget_exhausted") from exc
        raise


def run_wall_clock_bounded(method, *args):
    deadline = time.monotonic() + remaining_seconds(CHECK_BUDGET_S)

    def check():
        if time.monotonic() >= deadline:
            raise DoctorBudgetExhausted("doctor_check_budget_exhausted")

    return run_bounded(method, *args, check=check)
