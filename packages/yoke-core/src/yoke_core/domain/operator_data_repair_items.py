"""Resolve reviewed public item identities without exposing engine join keys."""

from pglast import ast, parse_sql
from pglast.stream import RawStream
from pglast.visitors import Visitor
from yoke_contracts.public_ref import parse_public_item_ref

from yoke_core.domain.item_ref_render import render_item_ref_lookup
from yoke_core.domain.operator_data_repair_sql import RepairRefusal


def snapshot_keys(plan):
    if any("item_id" in row for row in plan.before + plan.after):
        raise RepairRefusal(
            "internal_item_id_forbidden",
            "Use public_ref (PREFIX-N) instead of item_id in repair snapshots.",
        )
    if "public_ref" in plan.before[0]:
        if "item_id" not in plan.key_columns:
            raise RepairRefusal(
                "repair_item_key_required",
                "Use public_ref snapshots only for a primary key containing item_id; keep key_columns in catalog order.",
            )
        for row in plan.before + plan.after:
            ref = row.get("public_ref")
            if not isinstance(ref, str) or None in parse_public_item_ref(ref):
                raise RepairRefusal(
                    "public_item_ref_required",
                    "Every item snapshot must carry public_ref as a complete PREFIX-N reference.",
                )
    return ["public_ref" if key == "item_id" else key for key in plan.key_columns]


class _PublicItemColumn(Visitor):
    def __init__(self, refs):
        self.refs = refs

    def visit_ColumnRef(self, ancestors, node):
        if len(node.fields) == 1 and node.fields[0].sval == "public_ref":
            # Only reviewed identities participate in the virtual column. Exact
            # before/affected-key guards still reject any extra predicate match.
            return ast.CaseExpr(
                arg=ast.ColumnRef(fields=(ast.String(sval="item_id"),)),
                args=tuple(
                    ast.CaseWhen(
                        expr=ast.A_Const(val=ast.Integer(ival=item_id)),
                        result=ast.A_Const(val=ast.String(sval=ref)),
                    )
                    for ref, item_id in self.refs.items()
                ),
            )


def resolve_item_plan(conn, plan, project_id):
    if "public_ref" not in plan.before[0]:
        return plan, {}
    wanted = sorted({row["public_ref"] for row in plan.before})
    rows = conn.execute(
        "SELECT r.public_ref, r.item_id, r.project_id FROM public.item_refs r "
        "JOIN public.items i ON i.id=r.item_id "
        "JOIN public.projects p ON p.id=r.project_id "
        "WHERE r.public_ref = ANY(%s) FOR SHARE OF i, p",
        (wanted,),
    ).fetchall()
    refs = {ref: item_id for ref, item_id, _ in rows}
    if set(refs) != set(wanted):
        raise RepairRefusal(
            "repair_item_ref_unknown",
            "A reviewed public_ref no longer names an item; read current public references and review the document again.",
        )
    if any(owner != project_id for _, _, owner in rows):
        raise RepairRefusal(
            "repair_project_scope_mismatch",
            "Every public_ref must belong to the document's project; split the repair per project.",
        )

    def physical(row):
        return {
            **{key: value for key, value in row.items() if key != "public_ref"},
            "item_id": refs[row["public_ref"]],
        }

    tree = _PublicItemColumn(refs)(parse_sql(plan.sql))
    resolved = plan.model_copy(
        update={
            "sql": RawStream()(tree),
            "before": [physical(row) for row in plan.before],
            "after": [physical(row) for row in plan.after],
        }
    )
    return resolved, {item_id: ref for ref, item_id in refs.items()}


def public_snapshots(conn, rows, refs):
    if not refs:
        return rows
    unknown = {row["item_id"] for row in rows} - refs.keys()
    lookup = render_item_ref_lookup(conn, unknown) if unknown else None
    return [
        {
            **{key: value for key, value in row.items() if key != "item_id"},
            "public_ref": refs[row["item_id"]]
            if row["item_id"] in refs
            else lookup(row["item_id"]),
        }
        for row in rows
    ]
