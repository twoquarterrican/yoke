"""Live inventories the teaching prototype references but never copies.

Commands, functions and skills come from the registries that serve them,
documents and their links from the git-tracked tree, and plan entries from a
strategy document fetched by the person running the check.
"""

from __future__ import annotations

import json
import re
import subprocess
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[3]
_LINK = re.compile(r"\]\(([^)\s#]+)(?:#[^)\s]*)?\)")


def live_registries() -> dict:
    """Return command forms, function ids and skill ids served right now.

    Commands are the Atlas subcommand rows plus the client-local tool-shaped
    commands, the same two sources ``yoke --help`` lists.
    """
    from yoke_cli.commands.tool_shaped import TOOL_SHAPED_USAGE
    from yoke_contracts.skill_registry import SKILLS
    from yoke_core.tools.atlas_integrity_collect import (
        collect_function_registry,
        collect_subcommand_registry,
    )

    commands = {row["cli_form"]: row["function_id"]
                for row in collect_subcommand_registry()["rows"]}
    commands.update({form: None for form in TOOL_SHAPED_USAGE})
    functions = {row["function_id"] for row in collect_function_registry()["rows"]}
    skills = {skill.id for skill in SKILLS}
    return {"commands": commands, "functions": functions, "skills": skills}


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files"],
        check=True, capture_output=True, text=True,
    )
    return result.stdout.splitlines()


def documents(files: list[str]) -> dict:
    """Return tracked Markdown path -> resolved repository-relative link targets."""
    tracked = set(files)
    graph = {}
    for path in files:
        if not path.endswith(".md"):
            continue
        text = (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")
        targets = []
        for raw in _LINK.findall(text):
            if "://" in raw or raw.startswith("mailto:"):
                continue
            target = _normalize(PurePosixPath(path).parent / raw)
            if target in tracked and target not in targets:
                targets.append(target)
        graph[path] = targets
    return graph


def _normalize(path: PurePosixPath) -> str:
    parts: list[str] = []
    for part in path.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts)


def area_of(path: str, docs_graph: dict) -> str | None:
    """Return the first area whose globs include ``path``, else ``None``."""
    for area in docs_graph.get("areas", []):
        if any(fnmatch(path, glob) for glob in area["include"]) and not any(
            fnmatch(path, glob) for glob in area.get("exclude", [])
        ):
            return area["id"]
    return None


def strategy_entries(path: Path) -> tuple[str, str, list[str]]:
    """Return ``(slug, updated_at, expected row ids)`` from a strategy doc read.

    The input is the saved output of
    ``yoke strategy doc get SLUG --project yoke --json``. Expected ids cover
    every level-2 section, every FIRST-USER entry heading and every JOURNEYS
    principle, situation, owned-work clause and open question.
    """
    result = json.loads(path.read_text(encoding="utf-8"))["result"]
    slug, content = result["slug"], result["content"]
    ids: list[str] = []
    section = ""
    for line in content.splitlines():
        if line.startswith("## "):
            section = _slug(line[3:])
            ids.append(f"{slug}.{section}")
        elif slug == "FIRST-USER" and line.startswith("### "):
            entry = re.match(r"### ([0-9]+|[A-Z][0-9]*)\b", line)
            if entry:
                ids.append(f"{slug}.{entry.group(1)}")
        elif slug == "JOURNEYS":
            ids.extend(_journeys_entry(slug, section, line, ids))
    return slug, result["updated_at"], ids


def _journeys_entry(slug: str, section: str, line: str, seen: list[str]) -> list[str]:
    numbered = re.match(r"(\d+)\. ", line)
    row = re.match(r"\| (\d+) \|", line)
    if section == "locked-principles" and numbered:
        return [f"{slug}.principle-{numbered.group(1)}"]
    if section == "open-questions" and numbered:
        return [f"{slug}.question-{numbered.group(1)}"]
    if section == "situations-catalog" and row:
        return [f"{slug}.situation-{row.group(1)}"]
    if section == "also-owned-here" and line.startswith("- **"):
        count = sum(1 for item in seen if item.startswith(f"{slug}.owned-"))
        return [f"{slug}.owned-{count + 1}"]
    return []


def _slug(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
