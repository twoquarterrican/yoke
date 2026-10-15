"""Reuse prepared source answers while locked validation rereads durable facts."""

from contextlib import contextmanager
from contextvars import ContextVar

from yoke_core.domain.domain_refusal import DomainRefusal
from yoke_core.domain.schema_read_scope import shared_read

_VALIDATING = ContextVar("deployment_source_validation", default=False)


class SourcePreparationChanged(DomainRefusal, ValueError):
    """A changed source question needs a new unlocked preparation."""

    def __init__(self, message, prepare):
        super().__init__(message)
        self.prepare = prepare


def source_read(conn, key, reader):
    """One exact source question per operation; no provider work under locks."""

    def read():
        if _VALIDATING.get():
            raise SourcePreparationChanged(
                "deployment_source_preparation_changed: locked validation needs "
                "a source fact that was not prepared; nothing was dispatched. "
                "Re-drive the same run to prepare its current source facts "
                "before acquiring item/run locks.",
                lambda: shared_read(conn, key, reader),
            )
        return reader()

    return shared_read(conn, key, read)


@contextmanager
def prepared_sources_only():
    token = _VALIDATING.set(True)
    try:
        yield
    finally:
        _VALIDATING.reset(token)
