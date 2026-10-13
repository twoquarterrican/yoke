"""Local file navigation recovers through the private UI admission opener."""

from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from yoke_core.api.browser_return import browser_sign_in_redirect
from yoke_core.api.routes.shared_files import (
    is_browser_navigation,
    is_shared_file_browser_read,
)

SIGN_IN_PATH = "/file-sign-in"


def signed_out_file(request: Request, cookie: str) -> Response | None:
    if request.method == "GET" and request.url.path == SIGN_IN_PATH:
        return HTMLResponse(
            "<h1>Sign in to Yoke</h1><p>session_token_required: "
            "run <code>yoke ui up</code> in your terminal on this machine "
            "to open this view, then return to your file automatically.</p>",
            headers={"Cache-Control": "no-store"},
        )
    if is_shared_file_browser_read(request) and is_browser_navigation(request):
        response = browser_sign_in_redirect(request, cookie=cookie)
        response.headers["location"] = SIGN_IN_PATH
        return response
    return None
