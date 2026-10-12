"""``GET /v1/files/{project}/{path}`` — serve one shared file's bytes.

The URL ``files.upload`` returns stays usable indefinitely: each read signs
a fresh store URL server-side (or reads the serving machine's disk) and
streams the bytes back, so no expiring link ever reaches the reader. The
caller needs ``items.read`` on the project, by API token or by the browser's
workbench session cookie. Files are served in a sandboxed origin so an
uploaded HTML page cannot act as the signed-in reader.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from yoke_contracts.shared_files import (
    SHARED_FILE_ROUTE_PREFIX,
    SharedFilePathError,
    shared_file_content_type,
    shared_file_path,
    shared_file_project,
)

router = APIRouter()

#: Uploaded pages run scripts, but never as this server's origin.
_SANDBOX_POLICY = "sandbox allow-scripts allow-popups allow-forms allow-downloads"

_STATUS_BY_CODE = {
    SharedFilePathError.code: 400,
    "project_not_found": 404,
    "shared_file_not_found": 404,
    "shared_file_too_large": 413,
}


def is_shared_file_browser_read(request: Request) -> bool:
    """True for a cookie-carrying shared-file GET with no bearer header."""
    from yoke_core.api.web_session_auth import WEB_SESSION_COOKIE_NAME

    return (
        request.method.upper() == "GET"
        and request.url.path.startswith(f"{SHARED_FILE_ROUTE_PREFIX}/")
        and not request.headers.get("authorization")
        and bool(request.cookies.get(WEB_SESSION_COOKIE_NAME))
    )


def _refusal(code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=_STATUS_BY_CODE.get(code, 502),
    )


def shared_file_response(
    project: str,
    path: str,
    *,
    actor_id: Optional[int],
    download: bool = False,
) -> Response:
    """Serve one shared file, or a named refusal.

    ``actor_id=None`` is the machine-local operator (the loopback UI); a
    numeric actor must hold ``items.read`` on the project.
    """
    from yoke_core.domain.actor_permissions import PERM_ITEMS_READ
    from yoke_core.domain.actor_project_visibility import (
        actor_project_ids_with_permission,
    )
    from yoke_core.domain.db_helpers import connect
    from yoke_core.domain.project_identity import resolve_project
    from yoke_core.domain.shared_file_storage import SharedFileError, read_shared_file

    try:
        project = shared_file_project(project)
        path = shared_file_path(path)
    except SharedFilePathError as exc:
        return _refusal(exc.code, str(exc))
    with connect() as conn:
        visible = actor_project_ids_with_permission(conn, actor_id, PERM_ITEMS_READ)
        try:
            identity = resolve_project(
                conn, project, required=True, visible_project_ids=visible
            )
        except LookupError:
            return _refusal(
                "project_not_found",
                f"project {project!r} does not exist here or you lack items.read "
                "on it; ask a project admin for access",
            )
        assert identity is not None
        try:
            content = read_shared_file(
                conn, project_id=identity.id, project=identity.slug, path=path
            )
        except SharedFileError as exc:
            return _refusal(exc.code, str(exc))
    name = path.rsplit("/", 1)[-1]
    disposition = "attachment" if download else "inline"
    return Response(
        content=content,
        media_type=shared_file_content_type(path),
        headers={
            "Content-Disposition": f'{disposition}; filename="{name}"',
            "Content-Security-Policy": _SANDBOX_POLICY,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-cache",
        },
    )


@router.get("/files/{project}/{path:path}")
def read_shared_file_route(
    request: Request, project: str, path: str, download: bool = False
) -> Response:
    from yoke_core.api.http_auth import AUTH_STATE_ATTR
    from yoke_core.api.web_session_auth import WEB_AUTH_STATE_ATTR

    auth = getattr(request.state, AUTH_STATE_ATTR, None) or getattr(
        request.state, WEB_AUTH_STATE_ATTR, None
    )
    actor_id = getattr(auth, "actor_id", None)
    if actor_id is None:
        return JSONResponse(
            {
                "error": {
                    "code": "authentication_required",
                    "message": "sign in to this server's workbench in this "
                    "browser, or send an API token as Authorization: Bearer",
                }
            },
            status_code=401,
        )
    return shared_file_response(
        project, path, actor_id=int(actor_id), download=download
    )


__all__ = ["is_shared_file_browser_read", "router", "shared_file_response"]
