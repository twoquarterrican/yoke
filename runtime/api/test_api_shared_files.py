"""Shared-file upload and stable-URL reads through the real HTTP boundary."""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from runtime.api.auth_test_helpers import mint_api_auth_context
from runtime.api.fixtures.pg_testdb import test_database
from runtime.api.qa_artifact_read_test_support import seed_s3_configuration
from runtime.api.shared_file_test_support import fake_object_store
from yoke_contracts.api.function_call import (
    ActorContext,
    FunctionCallRequest,
    TargetRef,
)
from yoke_core.domain import qa_artifact_broker as broker
from yoke_core.domain import shared_file_storage as storage
from yoke_core.domain.actor_permissions import ROLE_VIEWER, grant_actor_project_role
from yoke_core.domain.actors import seed_human_actor
from yoke_core.domain.api_tokens import mint_token
from yoke_core.domain.handlers.__init_register__ import register_all_handlers
from yoke_core.domain.web_sessions import mint_web_session
from yoke_core.domain.yoke_function_registry import reset_registry_for_tests

HTML = b"<!doctype html><title>plan</title><script>1</script>"
ROUTE = "/v1/files/yoke/plans/review.html"


@pytest.fixture(autouse=True)
def _serving_machine(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(storage, "administered_elsewhere_env", lambda: "")
    for name in (
        broker.BUCKET_ENV,
        broker.PREFIX_ENV,
        broker.BROKER_URL_ENV,
        broker.TOKEN_FILE_ENV,
    ):
        monkeypatch.delenv(name, raising=False)
    reset_registry_for_tests()
    register_all_handlers()
    yield
    reset_registry_for_tests()


def _upload_envelope(path: str, content: bytes) -> dict:
    return FunctionCallRequest(
        function="files.upload",
        actor=ActorContext(actor_id="op", session_id="s-1"),
        target=TargetRef(kind="global"),
        payload={
            "project": "yoke",
            "path": path,
            "content_base64": base64.b64encode(content).decode("ascii"),
        },
    ).model_dump(mode="json")


def _clients(conn):
    from yoke_core.api.main import app

    owner = mint_api_auth_context(conn)
    viewer_id = seed_human_actor(conn, "viewer")
    grant_actor_project_role(
        conn,
        actor_id=viewer_id,
        project_id=owner.project_id,
        role_name=ROLE_VIEWER,
        granted_by_actor_id=owner.actor_id,
    )
    outsider_id = seed_human_actor(conn, "outsider")
    viewer = mint_token(conn, actor_id=viewer_id, name="viewer").raw_token
    outsider = mint_token(conn, actor_id=outsider_id, name="outsider").raw_token
    cookie = mint_web_session(conn, actor_id=viewer_id).raw_token
    conn.commit()
    return app, owner, viewer, outsider, cookie


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _counts(conn) -> tuple[int, int, int]:
    return tuple(
        conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("items", "qa_runs", "qa_artifacts")
    )


def test_two_authorized_clients_read_one_upload_from_server_disk() -> None:
    with test_database() as conn:
        app, owner, viewer, outsider, cookie = _clients(conn)
        before = _counts(conn)
        client = TestClient(app)
        uploaded = client.post(
            "/v1/functions/call",
            json=_upload_envelope("plans/review.html", HTML),
            headers=owner.headers,
        ).json()
        by_owner = client.get(ROUTE, headers=owner.headers)
        by_viewer = client.get(ROUTE, headers=_bearer(viewer))
        by_cookie = TestClient(app, cookies={"yoke_web_session": cookie}).get(ROUTE)
        by_outsider = client.get(ROUTE, headers=_bearer(outsider))
        anonymous = TestClient(app).get(ROUTE)
        download = client.get(f"{ROUTE}?download=1", headers=_bearer(viewer))
        missing = client.get(
            "/v1/files/yoke/plans/absent.html", headers=_bearer(viewer)
        )
        viewer_upload = client.post(
            "/v1/functions/call",
            json=_upload_envelope("x.md", b"x"),
            headers=_bearer(viewer),
        ).json()
        after = _counts(conn)

    assert uploaded["success"], uploaded.get("error")
    result = uploaded["result"]
    assert result["url_path"] == ROUTE
    assert result["backend"] == "local"
    assert result["bytes"] == len(HTML)
    for response in (by_owner, by_viewer, by_cookie):
        assert response.status_code == 200, response.text
        assert response.content == HTML
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        assert response.headers["content-security-policy"].startswith("sandbox ")
        assert response.headers["content-disposition"].startswith("inline")
    assert (
        download.headers["content-disposition"] == 'attachment; filename="review.html"'
    )
    assert by_outsider.status_code == 404
    assert by_outsider.json()["error"]["code"] == "project_not_found"
    assert anonymous.status_code == 401
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "shared_file_not_found"
    assert viewer_upload["error"]["code"] == "permission_denied"
    assert before == after


def test_s3_backed_url_survives_signed_link_expiry() -> None:
    with test_database() as conn, fake_object_store() as store:
        seed_s3_configuration(conn, bucket="yoke-prod-artifacts")
        app, owner, viewer, _outsider, _cookie = _clients(conn)
        client = TestClient(app)
        uploaded = client.post(
            "/v1/functions/call",
            json=_upload_envelope("plans/review.html", HTML),
            headers=owner.headers,
        ).json()
        store.advance(10_000)
        later = client.get(ROUTE, headers=_bearer(viewer))
        store.advance(10_000)
        again = client.get(ROUTE, headers=owner.headers)

    assert uploaded["success"], uploaded.get("error")
    assert uploaded["result"]["address"] == (
        "s3://yoke-prod-artifacts/shared-files/yoke/plans/review.html"
    )
    assert later.status_code == 200, later.text
    assert again.status_code == 200, again.text
    assert later.content == again.content == HTML


def test_invalid_path_is_a_named_refusal() -> None:
    with test_database() as conn:
        app, owner, *_rest = _clients(conn)
        client = TestClient(app)
        upload = client.post(
            "/v1/functions/call",
            json=_upload_envelope("../escape.html", HTML),
            headers=owner.headers,
        ).json()
        read = client.get("/v1/files/yoke/.hidden", headers=owner.headers)
    assert upload["error"]["code"] == "shared_file_path_invalid"
    assert read.status_code == 400
    assert read.json()["error"]["code"] == "shared_file_path_invalid"
