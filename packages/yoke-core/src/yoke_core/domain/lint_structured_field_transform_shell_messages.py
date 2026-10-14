"""Shared remediation messages for the structured-field lints.

Single-source-of-truth module shared by:

* :mod:`yoke_core.domain.lint_structured_field_transform_shell` — uses
  :data:`REMEDIATION_TEXT` as its denial body and :data:`REMEDIATION_API_FIRST`
  to point operators at the function-call surface.
* :mod:`yoke_core.domain.lint_shell_quoted_function_payload` — uses
  :data:`REMEDIATION_API_FIRST` to phrase its remediation.

The constants live here (not inside either lint module) so the lint files
themselves stay small and their recovery messages stay consistent.
"""

from __future__ import annotations

# The denial-emit site lives in the sibling
# ``lint_structured_field_transform_shell.evaluate``, which attaches the
# check-id line to the assembled reason (``REMEDIATION_TEXT`` +
# ``REMEDIATION_API_FIRST``) right before the deny envelope is built. The
# templates below carry the recovery text only.


REMEDIATION_TEXT = (
    "BLOCKED: structured-field transform via shell choreography.\n\n"
    "Detected pattern: read existing item content via `items get` or "
    "`sections get`, capture the content to a temp file / shell variable "
    "/ pipe-transformer, then write the transformed content back via "
    "`items update <field> --stdin` or `sections upsert --content-file`. "
    "This pattern hits quoting/empty-content friction and lacks "
    "idempotency.\n\n"
    "Use the Python-owned helper instead:\n\n"
    "  python3 -m yoke_core.domain.item_field_transform append-addendum"
    " \\\n"
    '    --item YOK-N --field <field> --heading "<heading>"'
    " --source <name> --stdin\n\n"
    "For Progress Log appends (or any safe append to an item_sections "
    "row), use `section-append` instead of read-then-`sections upsert` "
    "choreography:\n\n"
    "  python3 -m yoke_core.domain.item_field_transform section-append"
    " \\\n"
    '    --item YOK-N --section "Progress Log" --headline "<headline>"'
    " \\\n"
    "    --ordering 200 --source <name> --stdin\n\n"
    "For a full-field rewrite, write the complete intended content "
    "directly via `items update <field> --stdin` -- without the "
    "intermediate get + transform step.\n\n"
    "Suppression: `# lint:no-structured-transform-check` on the command "
    "body is audit-only (recorded as outcome=suppression_attempted) — the "
    "rule still denies."
)


REMEDIATION_API_FIRST: str = (
    "Function-call surface (preferred): dispatch through the typed registry "
    "from Python or HTTP — there is no shell-CLI meta-adapter for arbitrary "
    "function_id dispatch. For shell paths, use the named subcommand that "
    "covers the operation you need:\n\n"
    "  - Python: yoke_core.domain.yoke_function_dispatch.dispatch("
    "FunctionCallRequest(...))\n"
    "  - HTTP:   POST /api/functions/call (FunctionCallRequest JSON body)\n"
    "  - Shell:  use the named adapter below, for example "
    "`execute-structured-write`, `sections upsert`, `claim-work`, or "
    "`qa run-add`.\n\n"
    "Registered adapter inventory:\n"
    "  runtime/api/service_client_structured_api_adapter_inventory.py"
)


__all__ = [
    "REMEDIATION_TEXT",
    "REMEDIATION_API_FIRST",
]
