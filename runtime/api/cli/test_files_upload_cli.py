"""``yoke files upload`` prints the stable URL for the serving connection."""

from __future__ import annotations

import base64
import io
import json
from contextlib import redirect_stdout
from unittest.mock import patch

import pytest

from runtime.api.fixtures.pg_testdb import test_database
from runtime.api.universe_ui_server_test_support import _TOKEN, ui_client as ui_client
from yoke_cli.commands.adapters.files_cli import files_upload
from yoke_cli.transport.https import HttpsConnection
from yoke_contracts.api.function_call import FunctionCallResponse
from yoke_core.domain import shared_file_storage as storage

HOSTED = "https://app.upyoke.com/api/orgs/acme"


def _stored(request_payload: dict) -> FunctionCallResponse:
    path = request_payload["path"]
    return FunctionCallResponse(
        success=True,
        function="files.upload",
        request_id="upload",
        version="v1",
        result={"project": "yoke", "path": path, "url_path": f"/v1/files/yoke/{path}"},
    )


def _run(args: list[str], connection: HttpsConnection | None) -> tuple[int, str, dict]:
    sent: dict = {}

    def dispatch(*, function_id, target, payload, **_kwargs):
        sent.update(function_id=function_id, target=target.kind, payload=payload)
        return _stored(payload)

    out = io.StringIO()
    with (
        patch("yoke_cli.commands._helpers.call_dispatcher", side_effect=dispatch),
        patch(
            "yoke_cli.transport.https.resolve_https_connection", return_value=connection
        ),
        redirect_stdout(out),
    ):
        code = files_upload(args)
    return code, out.getvalue(), sent


def test_hosted_upload_prints_api_url(tmp_path) -> None:
    source = tmp_path / "review.html"
    source.write_bytes(b"<p>plan</p>")
    code, out, sent = _run(
        [str(source), "--path", "plans/review.html", "--project", "yoke"],
        HttpsConnection(api_url=HOSTED, token="t", env="hosted"),
    )
    assert code == 0
    assert out.strip() == f"{HOSTED}/v1/files/yoke/plans/review.html"
    assert sent["function_id"] == "files.upload"
    assert sent["target"] == "global"
    assert base64.b64decode(sent["payload"]["content_base64"]) == b"<p>plan</p>"


def test_local_upload_defaults_path_and_points_at_local_ui(tmp_path) -> None:
    source = tmp_path / "notes.md"
    source.write_bytes(b"# notes")
    code, out, sent = _run([str(source), "--project", "yoke", "--json"], None)
    assert code == 0
    assert sent["payload"]["path"] == "notes.md"
    assert (
        json.loads(out)["result"]["url"]
        == "http://127.0.0.1:8688/v1/files/yoke/notes.md"
    )


def test_unreadable_source_is_a_usage_error(tmp_path, capsys) -> None:
    assert files_upload([str(tmp_path / "absent.html"), "--project", "yoke"]) == 2
    assert "cannot read" in capsys.readouterr().err


@pytest.fixture()
def _local_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage, "administered_elsewhere_env", lambda: "")


def test_local_ui_serves_shared_file_behind_its_session_token(
    ui_client, _local_disk
) -> None:
    with test_database() as conn:
        storage.put_shared_file(
            conn, project_id=1, project="yoke", path="plans/a.md", content=b"# plan"
        )
        refused = ui_client.get("/v1/files/yoke/plans/a.md")
        served = ui_client.get(f"/v1/files/yoke/plans/a.md?token={_TOKEN}")
    assert refused.status_code == 401
    assert served.status_code == 200, served.text
    assert served.content == b"# plan"
    assert served.headers["content-type"] == "text/markdown; charset=utf-8"
