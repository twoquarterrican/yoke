"""``files.upload`` — store one shared file and return its read route.

The bytes land in the project's configured artifacts bucket, or in the
serving machine's permanent tree when none is declared. No item, QA or file
record is written: ``GET /v1/files/{project}/{path}`` resolves the same
location from the path alone.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from typing import Optional

from pydantic import BaseModel

from yoke_contracts.api.function_call import (
    FunctionCallRequest,
    FunctionError,
    HandlerOutcome,
)
from yoke_contracts.shared_files import (
    SharedFilePathError,
    shared_file_content_type,
    shared_file_path,
    shared_file_route,
)


class FilesUploadRequest(BaseModel):
    project: str
    path: str
    content_base64: str


class FilesUploadResponse(BaseModel):
    project: str
    path: str
    url_path: str
    backend: str
    address: str
    bytes: int
    sha256: str
    content_type: str
    url: Optional[str] = None


def _error(code: str, message: str, jsonpath: Optional[str] = None) -> HandlerOutcome:
    return HandlerOutcome(
        primary_success=False,
        error=FunctionError(code=code, message=message, jsonpath=jsonpath),
    )


def handle_files_upload(request: FunctionCallRequest) -> HandlerOutcome:
    from yoke_core.domain.db_helpers import connect
    from yoke_core.domain.project_identity import resolve_project
    from yoke_core.domain.shared_file_storage import SharedFileError, put_shared_file

    try:
        payload = FilesUploadRequest.model_validate(request.payload or {})
    except ValueError as exc:
        return _error("payload_invalid", str(exc), "$.payload")
    try:
        path = shared_file_path(payload.path)
    except SharedFilePathError as exc:
        return _error(exc.code, str(exc), "$.payload.path")
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        return _error(
            "payload_invalid",
            f"content_base64 is not valid base64: {exc}",
            "$.payload.content_base64",
        )
    with connect() as conn:
        try:
            project = resolve_project(conn, payload.project, required=True)
        except LookupError as exc:
            return _error("project_not_found", str(exc), "$.payload.project")
        assert project is not None
        try:
            stored = put_shared_file(
                conn,
                project_id=project.id,
                project=project.slug,
                path=path,
                content=content,
            )
        except SharedFilePathError as exc:
            return _error(exc.code, str(exc), "$.payload.project")
        except SharedFileError as exc:
            return _error(exc.code, str(exc))
    return HandlerOutcome(
        primary_success=True,
        result_payload={
            "project": project.slug,
            "path": path,
            "url_path": shared_file_route(project.slug, path),
            "backend": stored.backend,
            "address": stored.address,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "content_type": shared_file_content_type(path),
        },
    )


__all__ = ["FilesUploadRequest", "FilesUploadResponse", "handle_files_upload"]
