"""Released coverage remains evidence for the merge boundary."""

from yoke_core.domain import db_backend
from yoke_core.domain.db_helpers import instant_parameter
from yoke_core.domain.path_claims_landed_boundary import landing_for_boundary


def released_claims_for_boundary(conn, item_id: int) -> list[tuple[int, str]]:
    landing = landing_for_boundary(conn, item_id)
    if landing is None:
        return []
    p = "%s" if db_backend.connection_is_postgres(conn) else "?"
    rows = conn.execute(
        "SELECT id, integration_target FROM path_claims WHERE owner_kind='item' "
        f"AND owner_item_id={p} AND state='released' AND release_reason='landed' "
        f"AND released_at >= {p} ORDER BY id",
        (item_id, instant_parameter(conn, landing.landed_at)),
    ).fetchall()
    return [(int(row[0]), str(row[1] or "")) for row in rows]
