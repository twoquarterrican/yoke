"""Shared-file addressing: one project path names one stored file everywhere.

A shared file is ordinary bytes uploaded through ``files.upload`` and read
back through ``GET /v1/files/{project}/{path}``. Nothing records it: the
project and path alone derive the object key in the configured artifacts
bucket (``{prefix?}/shared-files/{project}/{path}``), the hosted signer key
(``tenants/{id}/shared-files/{project}/{path}``), and the serving machine's
permanent disk location (``~/.yoke/shared-files/{project}/{path}``).

Every mode validates paths with the same segment rule the hosted signer
enforces, so a path that uploads in one mode uploads in every mode.
"""

from __future__ import annotations

import mimetypes
import re

from yoke_contracts.api_urls import API_VERSION_PREFIX, join_api_url

SHARED_FILES_STORAGE_KIND = "shared-files"
SHARED_FILE_ROUTE_PREFIX = f"{API_VERSION_PREFIX}/files"
MAX_SHARED_FILE_PATH_SEGMENTS = 16

#: One path segment: starts alphanumeric; letters, digits, dot, underscore,
#: hyphen; at most 128 characters. Identical to the hosted signer's rule.
_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")

#: Extensions whose type must not depend on the host's mimetypes tables.
_CONTENT_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".json": "application/json",
}
_FALLBACK_CONTENT_TYPE = "application/octet-stream"


class SharedFilePathError(ValueError):
    """A project or path cannot address a shared file."""

    code = "shared_file_path_invalid"


def _segment(value: str, *, field: str) -> str:
    if not _SEGMENT.fullmatch(value):
        raise SharedFilePathError(
            f"{field} segment {value!r} is invalid: each segment starts with a "
            "letter or digit and uses only letters, digits, '.', '_' or '-' "
            "(at most 128 characters)"
        )
    return value


def shared_file_project(value: object) -> str:
    """Validate a project slug used as the first address segment."""
    return _segment(str(value or "").strip(), field="project")


def shared_file_path(value: object) -> str:
    """Validate a relative destination path such as ``plans/review.html``."""
    text = str(value or "").strip()
    segments = text.split("/")
    if not text or len(segments) > MAX_SHARED_FILE_PATH_SEGMENTS:
        raise SharedFilePathError(
            "path must be a relative path of 1 to "
            f"{MAX_SHARED_FILE_PATH_SEGMENTS} '/'-separated segments, "
            f"got {text!r}"
        )
    return "/".join(_segment(segment, field="path") for segment in segments)


def shared_file_route(project: str, path: str) -> str:
    """The server-relative read route for one shared file."""
    return (
        f"{SHARED_FILE_ROUTE_PREFIX}/{shared_file_project(project)}/"
        f"{shared_file_path(path)}"
    )


def shared_file_url(base_url: str, project: str, path: str) -> str:
    """The absolute read URL below a server's API base URL."""
    return join_api_url(base_url, shared_file_route(project, path))


def shared_file_content_type(path: str) -> str:
    """The served content type, derived from the path's extension."""
    name = path.rsplit("/", 1)[-1].lower()
    suffix = name[name.rfind(".") :] if "." in name else ""
    content_type = _CONTENT_TYPES.get(suffix) or mimetypes.guess_type(name)[0]
    content_type = content_type or _FALLBACK_CONTENT_TYPE
    if content_type.startswith("text/") or content_type == "application/json":
        return f"{content_type}; charset=utf-8"
    return content_type


__all__ = [
    "MAX_SHARED_FILE_PATH_SEGMENTS",
    "SHARED_FILES_STORAGE_KIND",
    "SHARED_FILE_ROUTE_PREFIX",
    "SharedFilePathError",
    "shared_file_content_type",
    "shared_file_path",
    "shared_file_project",
    "shared_file_route",
    "shared_file_url",
]
