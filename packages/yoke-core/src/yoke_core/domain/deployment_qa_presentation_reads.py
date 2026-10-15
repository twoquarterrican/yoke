"""Share QA facts during one read-only evaluation, including target occupancy."""

from contextvars import ContextVar
from functools import wraps

from yoke_core.domain.schema_read_scope import composition_reads, shared_read

_PRESENTATION = ContextVar("deployment_qa_presentation", default=False)


def presentation_operation(function):
    @wraps(function)
    def run(*args, **kwargs):
        outer = not presentation_active()
        token = _PRESENTATION.set(True)
        try:
            # A caller may have prepared sources before acquiring its locks.
            # QA evidence must be read anew after that boundary, never borrowed
            # from the caller's earlier evaluation.
            with composition_reads(isolated=outer):
                return function(*args, **kwargs)
        finally:
            _PRESENTATION.reset(token)

    return run


def presentation_active():
    return _PRESENTATION.get()


def presentation_read(conn, key, reader):
    return shared_read(conn, key, reader) if presentation_active() else reader()
