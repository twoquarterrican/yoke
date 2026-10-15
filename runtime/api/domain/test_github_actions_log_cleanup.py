"""GitHub job-log failures close responses before delayed garbage collection."""

from __future__ import annotations

import io
import urllib.error

import pytest

from yoke_core.domain import github_actions_logs as logs
from yoke_core.domain.gh_rest_transport import RestTransportError


class UnreadableBody(io.BytesIO):
    def read(self, size=-1):
        raise OSError("body unavailable")


@pytest.mark.parametrize("status", [401, 500])
@pytest.mark.parametrize("unreadable", [False, True])
@pytest.mark.parametrize("operation", [logs.fetch_job_log, logs.job_log_download_url])
def test_job_log_errors_close_owned_response_before_returning(
    monkeypatch, status, unreadable, operation
):
    body = UnreadableBody() if unreadable else io.BytesIO(b"provider error")
    error = urllib.error.HTTPError(
        "https://api.github.com/x", status, "synthetic", {}, body
    )

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(logs, "urlopen", fail)
    monkeypatch.setattr(logs, "no_redirect_urlopen", fail)
    monkeypatch.setattr(logs.gh_retry, "MAX_RETRIES", 1)

    with pytest.raises(RestTransportError) as caught:
        operation("example/repo", 1, token="test-token")

    assert caught.value.status == status
    assert body.closed
    assert error.closed
