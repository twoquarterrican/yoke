"""Thread-local Python cancellation without unwinding native driver protocols."""

from __future__ import annotations

import dis
import sys
from contextvars import ContextVar

_driver_active: ContextVar[bool] = ContextVar("deadline_driver_active", default=False)


def native_call(method, *args, **kwargs):
    token = _driver_active.set(True)
    try:
        return method(*args, **kwargs)
    finally:
        _driver_active.reset(token)


def run_bounded(method, *args, check):
    previous = sys.gettrace()
    looping_codes = {}

    def trace(frame, event, arg):
        if not _driver_active.get():
            check()
        if event == "call":
            code = frame.f_code
            loops = looping_codes.get(code)
            if loops is None:
                loops = looping_codes[code] = any(
                    (
                        instruction.opcode in dis.hasjrel
                        or instruction.opcode in dis.hasjabs
                    )
                    and isinstance(instruction.argval, int)
                    and instruction.argval <= instruction.offset
                    for instruction in dis.get_instructions(code)
                )
            if not loops:
                return None
        return trace

    sys.settrace(trace)
    try:
        result = method(*args)
        check()
        return result
    finally:
        sys.settrace(previous)
