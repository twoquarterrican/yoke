"""Human operator boundary for guarded control-plane row repair."""

from pydantic import BaseModel, ConfigDict, Field

from yoke_contracts.api.function_call import (
    FunctionCallRequest,
    FunctionError,
    HandlerOutcome,
)
from yoke_core.domain import db_backend, db_helpers
from yoke_core.domain.actor_permissions import PERM_ORG_ADMIN, PermissionDenied
from yoke_core.domain.control_plane_authority import require_control_plane_permission
from yoke_core.domain.operator_data_repair import RepairPlan, run_repair
from yoke_core.domain.operator_data_repair_sql import RepairRefusal


class RepairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: RepairPlan
    reviewed_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dry_run: bool = False


class RepairResponse(BaseModel):
    audit_id: int
    outcome: str
    sql_sha256: str
    review_sha256: str
    row_count: int


def handle_repair(request: FunctionCallRequest) -> HandlerOutcome:
    try:
        if request.actor.session_id or not str(request.actor.actor_id or "").isdigit():
            raise RepairRefusal(
                "human_operator_required",
                "Run operator data-repair as a signed-in human outside any harness session.",
            )
        try:
            body = RepairRequest.model_validate(request.payload)
        except Exception:
            raise RepairRefusal(
                "repair_payload_invalid",
                "The document does not match the repair schema; see yoke operator data-repair --help.",
            ) from None
        conn = db_helpers.connect()
        try:
            actor_id = int(request.actor.actor_id)
            require_control_plane_permission(
                conn, actor_id=actor_id, permission_key=PERM_ORG_ADMIN
            )
            marker = "%s" if db_backend.connection_is_postgres(conn) else "?"
            row = conn.execute(
                f"SELECT kind FROM actors WHERE id={marker}", (actor_id,)
            ).fetchone()
            if row is None or row[0] != "human":
                raise RepairRefusal(
                    "human_operator_required",
                    "Sign in as the control-plane human administrator to authorize this repair.",
                )
            if not db_backend.connection_is_postgres(conn):
                raise RepairRefusal(
                    "repair_postgres_required",
                    "Select the configured PostgreSQL control plane with yoke env list.",
                )
            result = run_repair(
                conn,
                body.plan,
                reviewed_sha256=body.reviewed_sha256,
                actor_id=actor_id,
                dry_run=body.dry_run,
            )
        finally:
            conn.close()
    except RepairRefusal as exc:
        return HandlerOutcome(
            primary_success=False, error=FunctionError(code=exc.code, message=str(exc))
        )
    except PermissionDenied:
        return HandlerOutcome(
            primary_success=False,
            error=FunctionError(
                code="operator_permission_required",
                message="Sign in as the control-plane organization administrator before authorizing row repair.",
            ),
        )
    except Exception:
        return HandlerOutcome(
            primary_success=False,
            error=FunctionError(
                code="repair_authority_unavailable",
                message="The control plane or its durable audit could not be read or written. Ask its operator to restore authority and reconcile planned operator_data_repair audit rows before retrying.",
            ),
        )
    return HandlerOutcome(result_payload=result)
