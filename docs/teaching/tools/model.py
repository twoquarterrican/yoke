"""Load, cross-check and canonically format the teaching prototype model.

Every model file is JSON under ``docs/teaching/model``. Loading never stops
at the first defect: each problem is collected with the file and record it
names, so one check run reports everything that needs repair.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

TEACHING_ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = TEACHING_ROOT / "model"
STATUSES = (
    "observed", "verified-live", "candidate", "approved",
    "deferred", "draft-copy", "superseded",
)
PLAN_MAPPING_KEYS = ("concepts", "surfaces", "scenarios", "boundaries", "gaps")
REBUILD = "yoke dev run -- python3 docs/teaching/tools/build.py"


@dataclass(frozen=True)
class Problem:
    code: str
    where: str
    message: str

    def render(self) -> str:
        return f"{self.code}: {self.where}: {self.message}"


@dataclass
class Model:
    concepts: dict = field(default_factory=dict)
    concept_files: list = field(default_factory=list)
    surfaces: dict = field(default_factory=dict)
    teaching: dict = field(default_factory=dict)
    scenarios: dict = field(default_factory=dict)
    lessons: dict = field(default_factory=dict)
    plan_files: list = field(default_factory=list)
    plan_rows: dict = field(default_factory=dict)
    evidence_files: list = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    boundaries: dict = field(default_factory=dict)
    gaps: dict = field(default_factory=dict)
    docs_graph: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)

    def problem(self, code: str, where: str, message: str) -> None:
        self.problems.append(Problem(code, where, message))


def dump(value) -> str:
    """Canonical model text: one-space indent, scalar lists kept inline."""
    return _format(value, 0) + "\n"


def _format(value, depth: int) -> str:
    pad = " " * depth
    if isinstance(value, dict) and value:
        items = [
            f"{pad} {json.dumps(key, ensure_ascii=False)}: {_format(item, depth + 1)}"
            for key, item in value.items()
        ]
        return "{\n" + ",\n".join(items) + f"\n{pad}}}"
    if isinstance(value, list) and any(isinstance(v, (dict, list)) for v in value):
        items = [f"{pad} {_format(item, depth + 1)}" for item in value]
        return "[\n" + ",\n".join(items) + f"\n{pad}]"
    return json.dumps(value, ensure_ascii=False)


def model_files() -> list[Path]:
    return sorted(MODEL_ROOT.rglob("*.json"))


def relative(path: Path) -> str:
    return path.relative_to(TEACHING_ROOT.parents[1]).as_posix()


def _read(model: Model, path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        model.problem("MODEL_UNREADABLE", relative(path), f"{error}; fix the JSON")
        return None


def _register(model: Model, table: dict, record_id: str, record: dict,
              where: str) -> None:
    if record_id in table:
        model.problem("DUPLICATE_ID", where, f"id {record_id!r} is defined twice")
    record["file"] = where
    table[record_id] = record


def load() -> Model:
    model = Model()
    concept_files = [(path, _read(model, path))
                     for path in sorted((MODEL_ROOT / "concepts").glob("*.json"))]
    concept_files.sort(key=lambda pair: (pair[1] or {}).get("parent") is not None)
    for path, data in concept_files:
        if data is not None:
            _load_concept_file(model, path, data)
    for path in sorted((MODEL_ROOT / "surfaces").glob("*.json")):
        data = _read(model, path)
        if data is not None:
            _load_owned(model, path, data, "surface", "teaching")
    for path in sorted((MODEL_ROOT / "scenarios").glob("*.json")):
        data = _read(model, path)
        if data is not None:
            _load_owned(model, path, data, "scenario", "lessons")
    for path in sorted((MODEL_ROOT / "plan").glob("*.json")):
        data = _read(model, path)
        if data is not None:
            data["stem"] = path.stem
            model.plan_files.append(data)
            for row in data.get("rows", []):
                _register(model, model.plan_rows, row["id"], row, relative(path))
    for path in sorted((MODEL_ROOT / "evidence").glob("*.json")):
        data = _read(model, path)
        if data is not None:
            data["stem"] = path.stem
            model.evidence_files.append(data)
            for record in data.get("records", []):
                _register(model, model.evidence, f"{path.stem}/{record['id']}",
                          record, relative(path))
    for name, table in (("boundaries", model.boundaries), ("gaps", model.gaps)):
        data = _read(model, MODEL_ROOT / f"{name}.json")
        for record in (data or {}).get("records", []):
            _register(model, table, record["id"], record,
                      relative(MODEL_ROOT / f"{name}.json"))
    model.docs_graph = _read(model, MODEL_ROOT / "docs-graph.json") or {}
    return model


def _load_concept_file(model: Model, path: Path, data: dict) -> None:
    parent = data.get("parent")
    where = relative(path)
    model.concept_files.append({"stem": path.stem, "parent": parent,
                                "roots": []})
    if parent is not None and parent not in model.concepts:
        model.problem("DANGLING_PARENT", where,
                      f"parent concept {parent!r} must load first; "
                      "name the file after its branch")
        return
    for node in data.get("nodes", []):
        full = _add_concept(model, node, parent, path.stem, where)
        model.concept_files[-1]["roots"].append(full)


def _add_concept(model: Model, node: dict, parent, stem: str,
                 where: str) -> str:
    full = node["id"] if parent is None else f"{parent}/{node['id']}"
    children = node.get("children", [])
    record = {k: v for k, v in node.items() if k != "children"}
    record.update(full_id=full, parent=parent, page=stem, children=[])
    _register(model, model.concepts, full, record, where)
    if parent is not None:
        model.concepts[parent]["children"].append(full)
    for child in children:
        _add_concept(model, child, full, stem, where)
    return full


def _load_owned(model: Model, path: Path, data: dict, kind: str,
                part: str) -> None:
    owner = data.get(kind, {})
    where = relative(path)
    owner_table = model.surfaces if kind == "surface" else model.scenarios
    part_table = model.teaching if kind == "surface" else model.lessons
    owner["page"] = path.stem
    _register(model, owner_table, owner.get("id", path.stem), owner, where)
    owner["parts"] = []
    for record in data.get(part, []):
        full = f"{owner['id']}/{record['id']}"
        record.update(full_id=full, owner=owner["id"], page=path.stem)
        _register(model, part_table, full, record, where)
        owner["parts"].append(full)


def all_records(model: Model):
    """Yield ``(kind, id, record)`` for every record that carries a status."""
    for kind, table in (
        ("concept", model.concepts), ("surface", model.surfaces),
        ("teaching", model.teaching), ("scenario", model.scenarios),
        ("lesson", model.lessons), ("plan", model.plan_rows),
        ("boundary", model.boundaries), ("gap", model.gaps),
        ("evidence", model.evidence),
    ):
        for record_id, record in table.items():
            yield kind, record_id, record


def validate(model: Model, live: dict, repo_files: set) -> None:
    """Check statuses, references, plan mappings and cited source paths.

    ``live`` maps ``commands``, ``functions`` and ``skills`` to the sets the
    live registries expose; ``repo_files`` is the git-tracked path set.
    """
    targets = {
        "plan_refs": model.plan_rows, "surface_refs": model.surfaces,
        "concepts": model.concepts, "topics": model.concepts,
        "surfaces": model.surfaces, "scenarios": model.scenarios,
        "related_scenarios": model.scenarios, "boundaries": model.boundaries,
        "gaps": model.gaps, "related": model.concepts,
        "commands": live["commands"], "functions": live["functions"],
        "skills": live["skills"],
    }
    for kind, record_id, record in all_records(model):
        where = f"{record.get('file', '?')}:{record_id}"
        status = record.get("status")
        if status not in STATUSES:
            model.problem("UNKNOWN_STATUS", where,
                          f"status {status!r} is not one of {', '.join(STATUSES)}")
        for key, table in targets.items():
            values = record.get(key)
            for value in [values] if isinstance(values, str) else values or []:
                if value not in table:
                    origin = ("live registry" if key in ("commands", "functions", "skills")
                              else "model")
                    model.problem("DANGLING_REFERENCE", where,
                                  f"{key} names {value!r}, absent from the {origin}")
        for source in record.get("sources", []):
            path = source.rsplit(":", 1)[0] if source.rsplit(":", 1)[-1].isdigit() else source
            if path not in repo_files:
                model.problem("DANGLING_SOURCE", where,
                              f"source {source!r} is not a tracked repository file")
        if kind == "plan" and not any(record.get(k) for k in PLAN_MAPPING_KEYS):
            model.problem("PLAN_ROW_UNMAPPED", where,
                          "map it to a concept, surface, scenario or boundary, "
                          "or name an explicit gap")
    for area in model.docs_graph.get("areas", []):
        for concept in area.get("concepts", []):
            if concept not in model.concepts:
                model.problem("DANGLING_REFERENCE", f"docs-graph.json:{area['id']}",
                              f"concepts names {concept!r}, absent from the model")


def coverage(model: Model) -> dict:
    """Return concept id -> sorted plan and teaching ids that map it.

    Only direct mappings count: a mapped parent never covers its children.
    """
    mapped = {concept_id: set() for concept_id in model.concepts}
    for concept_id, record in model.concepts.items():
        mapped[concept_id].update(record.get("plan_refs", []))
    for row_id, row in model.plan_rows.items():
        for concept_id in row.get("concepts", []):
            mapped.get(concept_id, set()).add(row_id)
    for teaching_id, record in model.teaching.items():
        for concept_id in record.get("topics", []):
            mapped.get(concept_id, set()).add(teaching_id)
    return {concept_id: sorted(ids) for concept_id, ids in mapped.items()}
