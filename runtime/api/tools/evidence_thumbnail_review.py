"""Serve production thumbnail components with extreme-aspect fixture images.

Run through ``yoke dev run -- env YOKE_ENV=render-proof python3 -m
runtime.api.tools.evidence_thumbnail_review`` from your own terminal; the
browser opens privately, then navigate to /thumbnail-review. Automated review
supplies its fixture token with ``--token``; no sign-in token is printed. The existing review server owns assets, authentication,
universe provenance, and /served-build; this tool adds only a fixture route.
"""

import argparse
from pathlib import Path

import uvicorn
from fastapi.responses import HTMLResponse

from runtime.api.tools.serve_workbench_for_review import (
    _free_port,
    prepare_review_database,
)
from yoke_core.ui.server import (
    UiServerError,
    create_ui_app,
    mint_session_token,
    private_url,
)
from yoke_cli.config.browser_admission import schedule_browser_admission
from yoke_core.ui.served_source_identity import served_build_identity
from yoke_core.ui.served_universe_connection import serving_connection


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--token", help="Explicit fixture token for automated review; never echoed."
    )
    arguments = parser.parse_args()
    if arguments.token is not None and not arguments.token.strip():
        parser.error(
            "review_fixture_token_empty: supply a non-empty fixture token or omit --token for private browser opening"
        )
    try:
        prepare_review_database()
    except UiServerError as exc:
        parser.exit(1, f"{exc}\n")
    port = _free_port()
    token = arguments.token or mint_session_token()
    app = create_ui_app(token, port=port)
    fixture_path = Path(__file__).with_suffix(".html")
    environment, _ = serving_connection()

    @app.get("/thumbnail-review")
    def thumbnails() -> HTMLResponse:
        return HTMLResponse(
            fixture_path.read_text()
            .replace("{{environment}}", str(environment))
            .replace("{{commit}}", served_build_identity()),
            headers={"Cache-Control": "no-store"},
        )

    print(f"review url: http://127.0.0.1:{port}/", flush=True)
    if arguments.token is None:
        schedule_browser_admission(private_url(port, token))
    print("fixture route: /thumbnail-review", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
