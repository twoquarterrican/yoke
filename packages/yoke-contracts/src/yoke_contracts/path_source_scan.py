"""Per-file source scanning for path-snapshot file entries.

Line count, language, module name and Python import edges for one file's
source; :func:`file_entry_from_source` assembles them into the entry the
snapshot payload carries.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional

from yoke_contracts.path_snapshot import SnapshotFileEntry

_LANGUAGE_BY_EXTENSION: Dict[str, str] = {
    ".py": "python",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".sh": "shell",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".html": "html",
    ".css": "css",
    ".sql": "sql",
}


@dataclass(frozen=True)
class ScanResult:
    edges: List[Dict[str, str]]
    error: Optional[str] = None


def compute_line_count(source: str) -> int:
    if not source:
        return 0
    return len(source.splitlines())


def infer_language(path_string: str) -> Optional[str]:
    lower = path_string.lower()
    for ext, lang in _LANGUAGE_BY_EXTENSION.items():
        if lower.endswith(ext):
            return lang
    return None


def path_to_module(path_string: str) -> str:
    if not path_string.endswith(".py"):
        return path_string
    p = PurePosixPath(path_string)
    parts = list(p.parts)
    if parts and parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = p.stem
    if "src" in parts:
        src_index = parts.index("src")
        package_parts = parts[src_index + 1 :]
        if package_parts and package_parts[0].startswith("yoke_"):
            return ".".join(package_parts)
    if parts[:2] == ["runtime", "api"]:
        return ".".join(["yoke_core", *parts[2:]])
    if parts[:2] == ["runtime", "harness"]:
        return ".".join(["yoke_harness", *parts[2:]])
    return ".".join(parts)


def compute_module_name(path_string: str) -> Optional[str]:
    if not path_string.endswith(".py"):
        return None
    return path_to_module(path_string)


def extract_edges(source: str, path_string: str) -> ScanResult:
    source_module = path_to_module(path_string)
    try:
        tree = ast.parse(source, filename=path_string)
    except SyntaxError as exc:
        return ScanResult(edges=[], error=f"SyntaxError: {exc}")
    edges: List[Dict[str, str]] = []
    import_aliases: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_module = alias.name
                imported_name = alias.asname or alias.name.split(".")[0]
                import_aliases[imported_name] = imported_module
                edges.append(
                    {
                        "source_module": source_module,
                        "imported_module": imported_module,
                        "imported_name": imported_name,
                    }
                )
        elif isinstance(node, ast.ImportFrom):
            module = _resolve_from_module(node, source_module)
            if module is None:
                continue
            for alias in node.names:
                name = alias.name
                imported_module = module
                if node.level > 0 and not node.module and name != "*":
                    imported_module = f"{module}.{name}" if module else name
                edges.append(
                    {
                        "source_module": source_module,
                        "imported_module": imported_module,
                        "imported_name": name,
                    }
                )
    _append_imported_attribute_edges(tree, source_module, import_aliases, edges)
    return ScanResult(edges=edges)


def _append_imported_attribute_edges(
    tree: ast.AST,
    source_module: str,
    import_aliases: Dict[str, str],
    edges: List[Dict[str, str]],
) -> None:
    seen = {
        (edge["source_module"], edge["imported_module"], edge["imported_name"])
        for edge in edges
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        value = node.value
        if not isinstance(value, ast.Name):
            continue
        imported_module = import_aliases.get(value.id)
        if not imported_module:
            continue
        triple = (source_module, imported_module, node.attr)
        if triple in seen:
            continue
        seen.add(triple)
        edges.append(
            {
                "source_module": source_module,
                "imported_module": imported_module,
                "imported_name": node.attr,
            }
        )


def _resolve_from_module(
    node: ast.ImportFrom,
    source_module: str,
) -> Optional[str]:
    if node.level == 0:
        return node.module or ""
    parts = source_module.split(".") if source_module else []
    if node.level > len(parts):
        return None
    base = parts[: len(parts) - node.level]
    if not node.module:
        return ".".join(base)
    return ".".join(base + node.module.split("."))


def file_entry_from_source(path_string: str, source: str) -> SnapshotFileEntry:
    scan = (
        extract_edges(source, path_string)
        if path_string.endswith(".py")
        else ScanResult(edges=[])
    )
    module_name = compute_module_name(path_string)
    edges: List[Dict[str, Any]] = list(scan.edges)
    if scan.error:
        edges = [
            {
                "source_module": module_name or path_string,
                "imported_module": "",
                "imported_name": "",
                "scan_error": scan.error,
            }
        ]
    return SnapshotFileEntry(
        path=path_string,
        line_count=compute_line_count(source),
        language=infer_language(path_string),
        module_name=module_name,
        dependency_edges=edges,
        scan_error=scan.error,
    )


__all__ = [
    "ScanResult",
    "compute_line_count",
    "compute_module_name",
    "extract_edges",
    "file_entry_from_source",
    "infer_language",
    "path_to_module",
]
