"""Share read-only Shipping QA facts for one member presentation operation."""

from contextvars import ContextVar
from functools import wraps

from yoke_core.domain.schema_read_scope import composition_reads, shared_read

_PRESENTATION = ContextVar("deployment_qa_presentation", default=False)


def presentation_operation(function):
    @wraps(function)
    def run(*args, **kwargs):
        token = _PRESENTATION.set(True)
        try:
            with composition_reads():
                return function(*args, **kwargs)
        finally:
            _PRESENTATION.reset(token)

    return run


def presentation_active():
    return _PRESENTATION.get()


def presentation_read(conn, key, reader):
    return shared_read(conn, key, reader) if presentation_active() else reader()
