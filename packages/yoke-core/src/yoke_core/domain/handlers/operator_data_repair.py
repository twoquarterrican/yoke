"""Steering-seat boundary for guarded control-plane row repair."""

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
from yoke_core.domain.project_identity import resolve_project_id
from yoke_core.domain.session_steering_authority import require_operator_seat
from yoke_core.domain.sessions_analytics_core import SessionError


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


def _repair_project_id(conn, project: str) -> int:
    try:
        return resolve_project_id(conn, project)
    except LookupError:
        raise RepairRefusal(
            "repair_project_unknown",
            f"The repair document names project {project!r}, which is not a registered project; name the project that owns the repaired rows.",
        ) from None


def handle_repair(request: FunctionCallRequest) -> HandlerOutcome:
    try:
        try:
            body = RepairRequest.model_validate(request.payload)
        except Exception:
            raise RepairRefusal(
                "repair_payload_invalid",
                "The document does not match the repair schema; see yoke operator data-repair --help.",
            ) from None
        if not str(request.actor.actor_id or "").isdigit():
            raise RepairRefusal(
                "operator_permission_required",
                "This call carries no authenticated actor; run it from a session registered to the organization administrator.",
            )
        actor_id = int(request.actor.actor_id)
        conn = db_helpers.connect()
        try:
            project_id = _repair_project_id(conn, body.plan.project)
            require_operator_seat(
                conn,
                caller_session_id=request.actor.session_id,
                project_id=project_id,
                action="Operator data-repair",
            )
            require_control_plane_permission(
                conn, actor_id=actor_id, permission_key=PERM_ORG_ADMIN
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
                project_id=project_id,
                dry_run=body.dry_run,
            )
        finally:
            conn.close()
    except RepairRefusal as exc:
        return HandlerOutcome(
            primary_success=False, error=FunctionError(code=exc.code, message=str(exc))
        )
    except SessionError as exc:
        return HandlerOutcome(
            primary_success=False,
            error=FunctionError(code=exc.code, message=exc.message),
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
