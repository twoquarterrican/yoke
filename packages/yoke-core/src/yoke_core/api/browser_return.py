"""Retain a same-origin file or approval destination through browser admission."""

from urllib.parse import unquote, urlsplit

from fastapi import Request
from fastapi.responses import RedirectResponse, Response

from yoke_contracts.machine_authorization import (
    APPROVAL_RETURN_COOKIE,
    CODE_TTL_SECONDS,
    approval_return_path,
)
from yoke_contracts.shared_files import (
    SHARED_FILE_ROUTE_PREFIX,
    SharedFilePathError,
    shared_file_path,
    shared_file_project,
)


def browser_return_path(value: str) -> str:
    """Allow only relative file URLs and the existing approval-page door."""
    if (
        not value
        or len(value) > 4096
        or not value.startswith("/")
        or value.startswith("//")
    ):
        return ""
    decoded = unquote(value)
    if any(ord(char) < 32 or char == "\\" for char in decoded):
        return ""
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.fragment or not value.startswith("/"):
        return ""
    if approval_return_path(value):
        return value
    prefix = SHARED_FILE_ROUTE_PREFIX + "/"
    path = unquote(parsed.path)
    if not path.startswith(prefix):
        return ""
    project, separator, name = path[len(prefix) :].partition("/")
    try:
        if not separator:
            return ""
        shared_file_project(project)
        shared_file_path(name)
    except SharedFilePathError:
        return ""
    return value


def remember_browser_return(
    response: Response, request: Request, *, cookie: str = APPROVAL_RETURN_COOKIE
) -> None:
    destination = browser_return_path(
        str(request.url.path) + ("?" + request.url.query if request.url.query else "")
    )
    if destination:
        response.set_cookie(
            cookie,
            destination,
            max_age=CODE_TTL_SECONDS,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
            path="/",
        )
    response.headers["Cache-Control"] = "no-store"


def browser_sign_in_redirect(
    request: Request, *, cookie: str = APPROVAL_RETURN_COOKIE
) -> Response:
    response = RedirectResponse("/", status_code=303)
    remember_browser_return(response, request, cookie=cookie)
    return response


def consume_browser_return(
    response: Response, request: Request, *, cookie: str = APPROVAL_RETURN_COOKIE
) -> str:
    destination = browser_return_path(request.cookies.get(cookie, ""))
    response.delete_cookie(cookie, path="/")
    return destination or "/"
