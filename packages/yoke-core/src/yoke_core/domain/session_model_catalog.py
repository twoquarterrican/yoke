"""Current catalog facts for capability decisions; pricing retains start time."""

from yoke_contracts.model_reference_records import ModelReferenceError
from yoke_core.domain.model_reference_store import revision_at


def current_model_records(conn):
    if conn is None:
        return ()
    try:
        return revision_at(conn)["records"]
    except ModelReferenceError:
        return ()
