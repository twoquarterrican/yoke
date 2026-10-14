"""Commit-clock release tags never allocate or move an immutable identity."""

from __future__ import annotations

import pytest

from yoke_contracts.api.function_call import (
    ActorContext,
    FunctionCallRequest,
    TargetRef,
)
from yoke_core.domain.gh_rest_transport_errors import (
    RestUnprocessableError,
)
from yoke_core.domain.handlers import github_commit_release_tag as subject


SOURCE = "a" * 40
TAG = "0.2.0.202610130941"


def request():
    return FunctionCallRequest(
        function="github.release.create_commit_tag",
        actor=ActorContext(actor_id="1", session_id="release-test"),
        target=TargetRef(kind="global", project_id="yoke"),
        payload={
            "repo": "upyoke/yoke",
            "project": "yoke",
            "source_sha": SOURCE,
            "summary": "Release the proven source.",
        },
    )


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(
        subject,
        "_validate_and_resolve",
        lambda req, model, *a, **kw: (
            model.model_validate(req.payload),
            "token",
            None,
        ),
    )
    state = {"ref": None, "source": SOURCE, "date": "2026-10-13T09:41:59Z"}
    writes = []

    def get(path, *, token):
        assert token == "token"
        if "/git/commits/" in path:
            return {"sha": state["source"], "committer": {"date": state["date"]}}
        if "/git/ref/" in path:
            assert path.endswith(TAG)
            if state["ref"] is None:
                return None
            return state["ref"]
        if "/git/tags/" in path:
            return {
                "tag": TAG,
                "object": {"type": "commit", "sha": state.get("target", SOURCE)},
            }
        raise AssertionError(path)

    def create(*args):
        writes.append(args)
        state["ref"] = {"object": {"type": "tag", "sha": "b" * 40}}

    monkeypatch.setattr(subject, "rest_get", get)
    monkeypatch.setattr(subject, "_create_annotated_tag", create)
    return state, writes


def test_create_uses_commit_clock_and_retry_recovers_same_tag(setup):
    state, writes = setup
    result = subject.handle_create_commit_release_tag(request())
    assert result.primary_success
    assert result.result_payload == {
        "tag": TAG,
        "version": TAG,
        "source_sha": SOURCE,
        "created": True,
    }
    assert writes == [
        ("upyoke/yoke", TAG, SOURCE, "Release the proven source.", "token")
    ]
    result = subject.handle_create_commit_release_tag(request())
    assert result.primary_success
    assert result.result_payload["created"] is False
    assert len(writes) == 1


@pytest.mark.parametrize(
    "ref,target",
    [
        ({"object": {"type": "commit", "sha": SOURCE}}, SOURCE),
        ({"object": {"type": "tag", "sha": "b" * 40}}, "c" * 40),
    ],
)
def test_collisions_refuse_without_writes(setup, ref, target):
    state, writes = setup
    state.update(ref=ref, target=target)
    result = subject.handle_create_commit_release_tag(request())
    assert not result.primary_success
    assert result.error.code == "release_tag_collision"
    assert "retry" in result.error.message
    assert not writes


def test_simultaneous_same_source_creation_recovers_ref(setup, monkeypatch):
    state, writes = setup

    def race(*args):
        state["ref"] = {"object": {"type": "tag", "sha": "b" * 40}}
        raise RestUnprocessableError("already exists", status=422)

    monkeypatch.setattr(subject, "_create_annotated_tag", race)
    result = subject.handle_create_commit_release_tag(request())
    assert result.primary_success
    assert result.result_payload["created"] is False
    assert not writes


def test_simultaneous_different_source_creation_refuses(setup, monkeypatch):
    state, writes = setup

    def race(*args):
        state.update(ref={"object": {"type": "tag", "sha": "b" * 40}}, target="c" * 40)
        raise RestUnprocessableError("already exists", status=422)

    monkeypatch.setattr(subject, "_create_annotated_tag", race)
    result = subject.handle_create_commit_release_tag(request())
    assert not result.primary_success
    assert result.error.code == "release_tag_collision"
    assert not writes


@pytest.mark.parametrize(
    "field,value", [("source", ""), ("date", ""), ("date", "2026-10-13T09:41:59")]
)
def test_missing_source_or_aware_clock_refuses(setup, field, value):
    state, writes = setup
    state[field] = value
    result = subject.handle_create_commit_release_tag(request())
    assert not result.primary_success
    assert result.error.code == "release_identity_invalid"
    assert "retry" in result.error.message
    assert not writes
