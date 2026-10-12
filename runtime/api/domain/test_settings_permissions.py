"""Yoke-managed permissions region merge/preserve/remove in settings.json."""

from __future__ import annotations

import json
from pathlib import Path

from yoke_cli.project_install.settings_permissions import (
    apply_settings_permissions,
    preview_settings_permissions,
    remove_settings_permissions,
)

_REL = ".claude/settings.json"
_MANAGED = {
    "allow": ["Bash", "Write(**)", "Edit(**)", "Read(*)", "Monitor"],
    "auto_memory_enabled": False,
}


def _write_settings(root: Path, payload: dict) -> None:
    target = root / _REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_settings(root: Path) -> dict:
    return json.loads((root / _REL).read_text(encoding="utf-8"))


def test_apply_adds_region_preserving_hooks_and_user_allow(tmp_path) -> None:
    _write_settings(
        tmp_path,
        {
            "hooks": {"PreToolUse": [{"matcher": "Bash"}]},
            "permissions": {"allow": ["MyTool"]},
        },
    )
    record, report = apply_settings_permissions(tmp_path, _MANAGED)
    settings = _read_settings(tmp_path)
    # user's own hook + allow entry survive; ours are unioned in
    assert settings["hooks"]["PreToolUse"] == [{"matcher": "Bash"}]
    assert settings["permissions"]["allow"][0] == "MyTool"
    assert "Monitor" in settings["permissions"]["allow"]
    assert settings["autoMemoryEnabled"] is False
    assert record["rendered_allow"] == _MANAGED["allow"]
    assert record["set_auto_memory"] is True
    assert report["changed"] is True


def test_apply_is_idempotent(tmp_path) -> None:
    _write_settings(tmp_path, {"hooks": {}})
    apply_settings_permissions(tmp_path, _MANAGED)
    _record, report = apply_settings_permissions(tmp_path, _MANAGED)
    assert report["changed"] is False
    assert "up to date" in report["actions"][0]


def test_does_not_overwrite_operator_auto_memory(tmp_path) -> None:
    _write_settings(tmp_path, {"hooks": {}, "autoMemoryEnabled": True})
    record, _ = apply_settings_permissions(tmp_path, _MANAGED)
    assert _read_settings(tmp_path)["autoMemoryEnabled"] is True  # operator choice kept
    assert record["set_auto_memory"] is False


def test_uninstall_removes_only_ours(tmp_path) -> None:
    _write_settings(
        tmp_path,
        {"hooks": {"X": [1]}, "permissions": {"allow": ["MyTool"]}},
    )
    record, _ = apply_settings_permissions(tmp_path, _MANAGED)
    result = remove_settings_permissions(tmp_path, record)
    settings = _read_settings(tmp_path)
    assert settings["permissions"]["allow"] == ["MyTool"]  # user's entry survives
    assert "autoMemoryEnabled" not in settings  # we seeded it, so we remove it
    assert settings["hooks"] == {"X": [1]}  # hook de-merge owns hooks
    assert "Monitor" in result["removed_allow"]
    assert result["deleted_file"] is False


def test_preview_does_not_write(tmp_path) -> None:
    _write_settings(tmp_path, {"hooks": {}})
    before = (tmp_path / _REL).read_text(encoding="utf-8")
    result = preview_settings_permissions(tmp_path, _MANAGED)
    assert result["would_change"] is True
    assert "Would update" in result["actions"][0]
    assert (tmp_path / _REL).read_text(encoding="utf-8") == before


def _retire_write(managed: dict) -> dict:
    return {**managed, "allow": [e for e in managed["allow"] if e != "Write(**)"]}


def test_refresh_removes_entry_yoke_stopped_rendering(tmp_path) -> None:
    _write_settings(tmp_path, {"hooks": {}, "permissions": {"allow": ["MyTool"]}})
    record, _ = apply_settings_permissions(tmp_path, _MANAGED)
    record, report = apply_settings_permissions(
        tmp_path, _retire_write(_MANAGED), record
    )
    allow = _read_settings(tmp_path)["permissions"]["allow"]
    assert "Write(**)" not in allow
    assert allow[0] == "MyTool"  # operator entry survives in place
    assert "Write(**)" not in record["rendered_allow"]
    assert "removed 1 retired Yoke permission(s)" in report["actions"][0]


def test_refresh_keeps_operator_entry_matching_no_record(tmp_path) -> None:
    _write_settings(tmp_path, {"hooks": {}, "permissions": {"allow": ["Custom(x)"]}})
    record, _ = apply_settings_permissions(tmp_path, _MANAGED)
    apply_settings_permissions(tmp_path, _retire_write(_MANAGED), record)
    assert "Custom(x)" in _read_settings(tmp_path)["permissions"]["allow"]


def test_first_refresh_with_prior_record_lacking_rendered_set_removes_nothing(
    tmp_path,
) -> None:
    _write_settings(tmp_path, {"hooks": {}})
    apply_settings_permissions(tmp_path, _MANAGED)
    older_record = {"added_allow": ["Write(**)"], "set_auto_memory": True}
    record, _ = apply_settings_permissions(
        tmp_path, _retire_write(_MANAGED), older_record
    )
    assert "Write(**)" in _read_settings(tmp_path)["permissions"]["allow"]
    assert "Write(**)" not in record["rendered_allow"]


def test_preview_names_retired_entries_without_writing(tmp_path) -> None:
    _write_settings(tmp_path, {"hooks": {}})
    record, _ = apply_settings_permissions(tmp_path, _MANAGED)
    before = (tmp_path / _REL).read_text(encoding="utf-8")
    result = preview_settings_permissions(tmp_path, _retire_write(_MANAGED), record)
    assert result["would_change"] is True
    assert "remove 1 retired Yoke permission(s)" in result["actions"][0]
    assert (tmp_path / _REL).read_text(encoding="utf-8") == before
