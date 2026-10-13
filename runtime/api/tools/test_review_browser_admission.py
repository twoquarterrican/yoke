"""Review commands preserve fixture admission without printing credentials."""

import pytest

from runtime.api.tools import serve_workbench_for_review as review
from runtime.api.tools import evidence_thumbnail_review as thumbnails
from yoke_cli.config import browser_admission as admission
from yoke_cli.config.hosted_machine_browser import BrowserOpenResult


@pytest.mark.parametrize("module", [review, thumbnails])
def test_empty_fixture_token_names_recovery(monkeypatch, capsys, module):
    monkeypatch.setattr("sys.argv", ["review", "--token", ""])
    with pytest.raises(SystemExit) as outcome:
        module.main()
    assert outcome.value.code == 2
    assert "review_fixture_token_empty" in capsys.readouterr().err


@pytest.mark.parametrize("fixture_token", [None, "explicit-fixture-token"])
def test_review_only_prints_bare_url(monkeypatch, capsys, fixture_token):
    served = []
    monkeypatch.setattr(review, "prepare_review_database", lambda: None)
    monkeypatch.setattr(review, "_free_port", lambda: 9876)
    monkeypatch.setattr(review.secrets, "token_urlsafe", lambda _: "generated-secret")
    monkeypatch.setattr(review, "serve_ui", lambda **kw: served.append(kw))
    args = ["review"] + (["--token", fixture_token] if fixture_token else [])
    monkeypatch.setattr("sys.argv", args)
    review.main()
    assert served == [
        {
            "port": 9876,
            "token": fixture_token or "generated-secret",
            "open_browser": fixture_token is None,
        }
    ]
    output = capsys.readouterr().out
    assert "http://127.0.0.1:9876/" in output
    assert "generated-secret" not in output
    assert "explicit-fixture-token" not in output
    assert "?token=" not in output


@pytest.mark.parametrize("fixture_token", [None, "explicit-fixture-token"])
def test_thumbnail_admission_is_private(monkeypatch, capsys, fixture_token):
    admissions, browser_urls = [], []

    class App:
        def get(self, path):
            return lambda handler: handler

    app = App()
    monkeypatch.setattr(thumbnails, "prepare_review_database", lambda: None)
    monkeypatch.setattr(thumbnails, "_free_port", lambda: 9876)
    monkeypatch.setattr(thumbnails, "mint_session_token", lambda: "generated-secret")
    monkeypatch.setattr(thumbnails, "serving_connection", lambda: ("review", None))
    monkeypatch.setattr(
        thumbnails, "create_ui_app", lambda token, **_: admissions.append(token) or app
    )
    monkeypatch.setattr(thumbnails, "schedule_browser_admission", browser_urls.append)
    monkeypatch.setattr(thumbnails.uvicorn, "run", lambda *_args, **_kw: None)
    args = ["thumbnail-review"] + (["--token", fixture_token] if fixture_token else [])
    monkeypatch.setattr("sys.argv", args)
    thumbnails.main()
    assert admissions == [fixture_token or "generated-secret"]
    assert browser_urls == (
        [] if fixture_token else ["http://127.0.0.1:9876/?token=generated-secret"]
    )
    output = capsys.readouterr().out
    assert "http://127.0.0.1:9876/" in output
    assert "generated-secret" not in output
    assert "explicit-fixture-token" not in output
    assert "?token=" not in output


def test_delayed_open_reports_safe_recovery(monkeypatch, capsys):
    calls = []

    class Timer:
        def __init__(self, delay, callback):
            self.callback = callback
            calls.append(delay)

        def start(self):
            self.callback()

    monkeypatch.setattr(admission.threading, "Timer", Timer)
    monkeypatch.setattr(
        admission,
        "open_private_url",
        lambda url: BrowserOpenResult(opened=False, reason="browser_agent_mode"),
    )
    admission.schedule_browser_admission("http://localhost/?token=private-secret")
    output = capsys.readouterr().err
    assert "browser_agent_mode" in output
    assert "your own terminal" in output
    assert "private-secret" not in output
    assert len(calls) == 1
