"""Item update validation CLI command.

Owns ``validate-update`` — an **internal validator**, not an agent-facing
work-item entrypoint. It only calls ``mutations.prepare_update`` to return
planned writes. Items are created through the registered ``items.create``
operation, which requires the spec with the title.
"""

from __future__ import annotations

import json
import sys

from yoke_core.domain import db_backend
from yoke_core.domain.project_identity_item_ref import item_ref_for_id
from yoke_core.domain.item_ref_resolution import ITEM_REF_NOT_FOUND
from yoke_core.api.service_client_shared import (
    _get_db_readonly,
    _load_gate_context,
    _load_item_state,
    _mutation_result_to_dict,
    mutations,
)


def cmd_update_item(args: list[str]) -> int:
    """Validate and prepare a single-field item update via the shared mutation layer.

    Usage: validate-update <PREFIX-N> --field FIELD --value VALUE
                           [--done-nonce-verified] [--force] [--qa-bypass]

    Returns JSON on stdout with the mutation result (field_writes, events).
    The caller (shell adapter) is responsible for applying the DB writes
    and post-update side effects.

    Exit 0: valid, JSON result on stdout
    Exit 1: validation/gate error, JSON error on stdout
    """
    if len(args) < 1:
        print(
            "Usage: validate-update <PREFIX-N> --field FIELD --value VALUE "
            "[--done-nonce-verified] [--force] [--qa-bypass]",
            file=sys.stderr,
        )
        return 2

    try:
        from yoke_core.api.service_client_shared_session_resolver import (
            _parse_item_id_arg,
        )

        item_id = _parse_item_id_arg(args[0])
    except ValueError as exc:
        missing = getattr(exc, "code", None) == ITEM_REF_NOT_FOUND
        print(
            json.dumps(
                {
                    "success": False,
                    "error": str(exc),
                    "error_code": "NOT_FOUND" if missing else "VALIDATION_ERROR",
                }
            )
        )
        return 1

    field_name = None
    value = None
    done_nonce_verified = False
    force = False
    qa_bypass = False

    i = 1
    while i < len(args):
        if args[i] == "--field" and i + 1 < len(args):
            field_name = args[i + 1]
            i += 2
        elif args[i] == "--value" and i + 1 < len(args):
            value = args[i + 1]
            i += 2
        elif args[i] == "--done-nonce-verified":
            done_nonce_verified = True
            i += 1
        elif args[i] == "--force":
            force = True
            i += 1
        elif args[i] == "--qa-bypass":
            qa_bypass = True
            i += 1
        else:
            print(f"Unknown argument: {args[i]}", file=sys.stderr)
            return 2

    if field_name is None or value is None:
        print(
            "Usage: validate-update <PREFIX-N> --field FIELD --value VALUE "
            "[--done-nonce-verified] [--force] [--qa-bypass]",
            file=sys.stderr,
        )
        return 2

    conn = _get_db_readonly()
    try:
        p = "%s" if db_backend.connection_is_postgres(conn) else "?"
        row = conn.execute(
            "SELECT i.*, pr.slug AS project FROM items i "
            "JOIN projects pr ON pr.id = i.project_id "
            f"WHERE i.id = {p}",
            (item_id,),
        ).fetchone()
        if row is None:
            print(
                json.dumps(
                    {
                        "success": False,
                        "error": f"Item {item_ref_for_id(item_id)} not found",
                        "error_code": "NOT_FOUND",
                    }
                )
            )
            return 1

        item_dict = dict(row)
        item_state = _load_item_state(conn, item_id)
        if item_state is None:
            print(
                json.dumps(
                    {
                        "success": False,
                        "error": f"Item {item_ref_for_id(item_id)} not found",
                        "error_code": "NOT_FOUND",
                    }
                )
            )
            return 1

        if field_name == "deployment_flow" and value:
            from yoke_core.domain.deployment_flow_validator import (
                validate_and_lookup_flow_project,
            )

            _flow_project, flow_err = validate_and_lookup_flow_project(
                conn, value, item_dict.get("project")
            )
            if flow_err:
                print(
                    json.dumps(
                        {
                            "success": False,
                            "error": flow_err,
                            "error_code": "VALIDATION_ERROR",
                            "preflight_only": True,
                        }
                    )
                )
                return 1

        target_status = value if field_name == "status" else None

        gate = _load_gate_context(
            conn,
            item_dict,
            target_status=target_status,
            deployment_flow_value=value if field_name == "deployment_flow" else None,
            deployed_to_value=value if field_name == "deployed_to" else None,
            done_nonce_verified=done_nonce_verified,
            force=force,
            qa_bypass=qa_bypass,
        )

        result = mutations.prepare_update(
            item=item_state,
            field_name=field_name,
            value=value,
            gate=gate,
        )

        payload = _mutation_result_to_dict(result)
        payload["preflight_only"] = True
        print(json.dumps(payload))
        return 0 if result.success else 1
    finally:
        conn.close()
