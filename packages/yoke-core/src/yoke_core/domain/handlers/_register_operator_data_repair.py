"""Register the human operator's guarded SQL repair boundary."""

from yoke_core.domain.handlers import operator_data_repair as repair


def register(registry) -> None:
    registry.register(
        "operator.data_repair.run",
        repair.handle_repair,
        repair.RepairRequest,
        repair.RepairResponse,
        stability="stable",
        owner_module="yoke_core.domain.handlers.operator_data_repair",
        target_kinds=["global"],
        side_effects=["guarded_control_plane_row_repair", "migration_audit_insert"],
        emitted_event_names=[],
        guardrails=[
            "authenticated_human_admin",
            "review_digest",
            "single_transactional_statement",
            "exact_before_after_rows",
            "durable_audit",
        ],
        adapter_status="live",
        claim_required_kind=None,
        ambient_session_required=False,
        minimum_serving_version="next-release",
    )
