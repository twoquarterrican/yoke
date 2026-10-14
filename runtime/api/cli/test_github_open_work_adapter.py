"""``yoke github open-work list`` dispatches the open-work read and stays short."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest import mock

from yoke_cli.commands.adapters import github_open_work as adapter
from yoke_cli.commands.flag_adapters import ADAPTER_USAGE
from yoke_cli.commands.registry import SUBCOMMAND_REGISTRY


def _dispatched(argv: list[str]) -> dict:
    with mock.patch.object(adapter, "dispatch_and_emit", return_value=0) as call:
        assert adapter.github_open_work_list(argv) == 0
    return call.call_args.kwargs


def test_routes_to_the_open_work_read() -> None:
    function_id, handler = SUBCOMMAND_REGISTRY[("github", "open-work", "list")]
    assert function_id == "github.open_work.list"
    assert handler is adapter.github_open_work_list
    assert ADAPTER_USAGE[function_id] == adapter.GITHUB_OPEN_WORK_LIST_USAGE


def test_the_server_owns_the_default_limit() -> None:
    kwargs = _dispatched(["--project", "widgets"])
    assert kwargs["function_id"] == "github.open_work.list"
    assert kwargs["target"].kind == "global"
    assert kwargs["payload"] == {"project": "widgets"}


def test_limit_and_json_pass_through() -> None:
    kwargs = _dispatched(["--project", "widgets", "--limit", "7", "--json", "--full"])
    assert kwargs["payload"] == {"project": "widgets", "limit": 7}
    assert kwargs["json_mode"] is True


def test_project_is_required(capsys) -> None:
    assert adapter.github_open_work_list([]) == 2
    assert "--project" in capsys.readouterr().err


def _render(result: dict) -> str:
    out = io.StringIO()
    adapter._write_open_work(SimpleNamespace(result=result), out, io.StringIO())
    return out.getvalue()


def test_human_reply_shows_counts_and_first_rows_under_forty_lines() -> None:
    issues = [
        {"number": n, "title": f"issue {n}", "labels": ["bug"] if n == 1 else []}
        for n in range(1, 101)
    ]
    pulls = [
        {"number": n, "title": f"pull {n}", "head_ref": f"b{n}", "draft": n == 200}
        for n in range(200, 300)
    ]
    text = _render(
        {
            "repo": "acme/widgets",
            "issues": issues,
            "pull_requests": pulls,
            "truncated": True,
        }
    )
    lines = text.splitlines()
    assert len(lines) < 40
    assert lines[0] == "Repository: acme/widgets"
    assert "Open issues: 100" in lines
    assert "Open pull requests: 100" in lines
    assert "  #1 issue 1 [bug]" in lines
    assert "  #200 pull 200 (draft) <- b200" in lines
    hidden = 100 - adapter.HUMAN_ROWS_PER_LIST
    assert lines.count(f"  ... {hidden} more; --json lists every row") == 2
    assert "More open work exists" in lines[-1]


def test_a_small_repository_lists_everything_without_a_more_line() -> None:
    text = _render(
        {
            "repo": "acme/widgets",
            "issues": [],
            "pull_requests": [
                {"number": 4, "title": "fix", "head_ref": "fix", "draft": False}
            ],
            "truncated": False,
        }
    )
    assert text.splitlines() == [
        "Repository: acme/widgets",
        "Open issues: 0",
        "Open pull requests: 1",
        "  #4 fix <- fix",
    ]
