"""Resolve reviewed public item identities without exposing engine join keys."""

from pglast import ast, parse_sql
from pglast.stream import RawStream
from pglast.visitors import Visitor
from yoke_contracts.item_identity_keys import engine_key_for_wire, wire_key_for_engine
from yoke_contracts.public_ref import parse_public_item_ref

from yoke_core.domain.item_ref_render import render_item_ref_lookup
from yoke_core.domain.operator_data_repair_sql import RepairRefusal


def snapshot_keys(plan):
    rows = plan.before + plan.after
    offending = next(
        (
            key
            for row in rows
            for key in row
            if wire_key_for_engine(key) or "item_id" in key
        ),
        None,
    )
    if offending is not None:
        wire = wire_key_for_engine(offending) or "public_ref"
        raise RepairRefusal(
            "internal_item_id_forbidden",
            f"Use {wire} (PREFIX-N) instead of {offending} in repair snapshots.",
        )
    for row in rows:
        for key, value in row.items():
            if not engine_key_for_wire(key) or value is None:
                continue
            if not isinstance(value, str) or None in parse_public_item_ref(value):
                raise RepairRefusal(
                    "public_item_ref_required",
                    f"Every {key} snapshot value must be a complete PREFIX-N reference.",
                )
    return [wire_key_for_engine(key) or key for key in plan.key_columns]


class _PublicItemColumn(Visitor):
    def __init__(self, columns):
        self.columns = columns

    def visit_ColumnRef(self, ancestors, node):
        if len(node.fields) != 1 or not isinstance(node.fields[0], ast.String):
            return None
        spec = self.columns.get(node.fields[0].sval)
        if spec is None:
            return None
        physical, refs = spec
        # Only reviewed before-identities participate in a comparison. Exact
        # before/affected-key guards still reject any extra predicate match.
        return ast.CaseExpr(
            arg=ast.ColumnRef(fields=(ast.String(sval=physical),)),
            args=tuple(
                ast.CaseWhen(
                    expr=ast.A_Const(val=ast.Integer(ival=item_id)),
                    result=ast.A_Const(val=ast.String(sval=ref)),
                )
                for ref, item_id in refs.items()
            ),
        )


def item_reference_columns(conn, table):
    """Physical columns that store ``items.id``.

    A foreign key to ``items.id`` qualifies. So does an ``item_id`` column
    with no foreign key: several live tables, including ``qa_requirements``,
    store the id without declaring one. A foreign key to any other table
    does not.
    """
    rows = conn.execute(
        "SELECT a.attname, "
        "EXISTS (SELECT 1 FROM pg_catalog.pg_constraint c "
        "JOIN pg_catalog.pg_class f ON f.oid=c.confrelid "
        "JOIN pg_catalog.pg_namespace fn ON fn.oid=f.relnamespace "
        "JOIN pg_catalog.pg_attribute fa ON fa.attrelid=c.confrelid "
        "AND fa.attnum=ANY(c.confkey) "
        "WHERE c.conrelid=a.attrelid AND c.contype='f' AND a.attnum=ANY(c.conkey) "
        "AND fn.nspname='public' AND f.relname='items' AND fa.attname='id'), "
        "EXISTS (SELECT 1 FROM pg_catalog.pg_constraint c "
        "WHERE c.conrelid=a.attrelid AND c.contype='f' AND a.attnum=ANY(c.conkey)) "
        "FROM pg_catalog.pg_attribute a "
        "WHERE a.attrelid=%s::regclass AND a.attnum>0 AND NOT a.attisdropped",
        (f"public.{table}",),
    ).fetchall()
    return {
        name
        for name, refs_items, has_fk in rows
        if wire_key_for_engine(name) and (refs_items or not has_fk)
    }


def _string_literal(node):
    value = getattr(node, "val", None)
    if isinstance(value, ast.String):
        return value.sval
    return None


def _sql_virtual_names(tree):
    names = set()

    def walk(node):
        if isinstance(node, ast.Node):
            if (
                isinstance(node, ast.ColumnRef)
                and len(node.fields) == 1
                and isinstance(node.fields[0], ast.String)
                and engine_key_for_wire(node.fields[0].sval)
            ):
                names.add(node.fields[0].sval)
            for field in node:
                walk(getattr(node, field))
        elif isinstance(node, (tuple, list)):
            for child in node:
                walk(child)

    for raw in tree:
        stmt = raw.stmt
        for target in getattr(stmt, "targetList", None) or ():
            if engine_key_for_wire(target.name):
                names.add(target.name)
            walk(target.val)
        walk(stmt.whereClause)
    return names


def _assign_item_ids(tree, mapping, refs):
    for raw in tree:
        for target in getattr(raw.stmt, "targetList", None) or ():
            physical = mapping.get(target.name)
            if physical is None:
                continue
            target.name = physical
            literal = _string_literal(target.val)
            if literal is None:
                continue
            item_id = refs.get(literal)
            if item_id is None:
                raise RepairRefusal(
                    "repair_item_ref_unknown",
                    "An assigned public ref no longer names an item; read current public references and review the document again.",
                )
            target.val = ast.A_Const(val=ast.Integer(ival=item_id))


def _load_item_refs(conn, wanted, project_id):
    if not wanted:
        return {}
    rows = conn.execute(
        "SELECT r.public_ref, r.item_id, r.project_id FROM public.item_refs r "
        "JOIN public.items i ON i.id=r.item_id "
        "JOIN public.projects p ON p.id=r.project_id "
        "WHERE r.public_ref = ANY(%s) FOR SHARE OF i, p",
        (wanted,),
    ).fetchall()
    if {row[0] for row in rows} != set(wanted):
        raise RepairRefusal(
            "repair_item_ref_unknown",
            "A reviewed public_ref no longer names an item; read current public references and review the document again.",
        )
    if any(row[2] != project_id for row in rows):
        raise RepairRefusal(
            "repair_project_scope_mismatch",
            "Every public_ref must belong to the document's project; split the repair per project.",
        )
    return {row[0]: row[1] for row in rows}


def resolve_item_plan(conn, plan, project_id):
    tree = parse_sql(plan.sql)
    virtual_names = {
        key
        for row in plan.before + plan.after
        for key in row
        if engine_key_for_wire(key)
    } | _sql_virtual_names(tree)
    if not virtual_names:
        return plan, {}
    physical_columns = item_reference_columns(conn, plan.table)
    mapping = {}
    for name in virtual_names:
        physical = engine_key_for_wire(name)
        if physical not in physical_columns:
            raise RepairRefusal(
                "repair_column_type_refused",
                f"{name} does not reference items.id on {plan.table}; use the public_ref form of a column that stores an item id, then review the document again.",
            )
        mapping[name] = physical
    wanted = sorted(
        {
            row[name]
            for row in plan.before + plan.after
            for name in mapping
            if name in row and row[name] is not None
        }
    )
    refs = _load_item_refs(conn, wanted, project_id)

    def physical_row(row):
        return {
            mapping.get(key, key): (None if value is None else refs[value])
            if key in mapping
            else value
            for key, value in row.items()
        }

    before_maps = {
        name: (
            physical,
            {
                row[name]: refs[row[name]]
                for row in plan.before
                if name in row and row[name] is not None
            },
        )
        for name, physical in mapping.items()
    }
    _assign_item_ids(tree, mapping, refs)
    rewritten = _PublicItemColumn(before_maps)(tree)
    resolved = plan.model_copy(
        update={
            "sql": RawStream()(rewritten),
            "before": [physical_row(row) for row in plan.before],
            "after": [physical_row(row) for row in plan.after],
        }
    )
    column_refs = {
        physical: {
            refs[row[name]]: row[name]
            for row in plan.before + plan.after
            if name in row and row[name] is not None
        }
        for name, physical in mapping.items()
    }
    return resolved, column_refs


def public_snapshots(conn, rows, column_refs):
    if not column_refs:
        return rows
    unknown = {
        row[column]
        for row in rows
        for column, known in column_refs.items()
        if column in row and row[column] is not None and row[column] not in known
    }
    lookup = render_item_ref_lookup(conn, unknown) if unknown else None
    rendered = []
    for row in rows:
        out = dict(row)
        for column, known in column_refs.items():
            if column not in out:
                continue
            item_id = out.pop(column)
            wire = wire_key_for_engine(column)
            if item_id is None:
                out[wire] = None
            elif item_id in known:
                out[wire] = known[item_id]
            else:
                out[wire] = lookup(item_id)
        rendered.append(out)
    return rendered
