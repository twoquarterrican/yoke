"""Compatibility exports for path-snapshot dependency scanning helpers."""

from __future__ import annotations

from yoke_contracts.path_source_scan import (
    ScanResult,
    extract_edges,
    path_to_module,
)

__all__ = [
    "ScanResult",
    "extract_edges",
    "path_to_module",
]
