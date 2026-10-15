"""Share current QA facts within one evaluation, independently of source caches."""

from contextvars import ContextVar
from functools import wraps

from yoke_core.domain.schema_read_scope import composition_reads

_PRESENTATION = ContextVar("deployment_qa_presentation", default=None)


def presentation_operation(function):
    @wraps(function)
    def run(*args, **kwargs):
        token = _PRESENTATION.set({}) if not presentation_active() else None
        try:
            # Immutable source answers may be reused by the enclosing operation;
            # mutable QA facts belong only to this evaluation after its locks.
            with composition_reads():
                return function(*args, **kwargs)
        finally:
            if token is not None:
                _PRESENTATION.reset(token)

    return run


def presentation_active():
    return _PRESENTATION.get() is not None


def presentation_read(conn, key, reader):
    cache = _PRESENTATION.get()
    if cache is None:
        return reader()
    scoped_key = (conn, key)
    if scoped_key not in cache:
        cache[scoped_key] = reader()
    return cache[scoped_key]
