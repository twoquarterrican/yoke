"""Translate uv shell setup into onboarding plan steps."""

from __future__ import annotations

from typing import Any

from yoke_cli.config import path_repair_plan


PATH_REPAIR_ACTION = "update-shell-path"


def steps(plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not plan or plan.get("login_verified"):
        return []
    return [
        {
            "action": PATH_REPAIR_ACTION,
            "target": str(target.get("path") or ""),
            "surface": str(target.get("surface") or ""),
            "path_repair": plan,
        }
        for target in plan.get("targets", [])
    ]


def friendly_line(step: dict[str, Any]) -> str:
    plan = step.get("path_repair") or {}
    target = {
        "path": step.get("target"),
        "surface": step.get("surface"),
    }
    return path_repair_plan.target_description(target, plan)


def shell_change_lines(plan: dict[str, Any] | None) -> list[str]:
    return [
        f"Shell file updated: {path}" for path in (plan or {}).get("changed_files", [])
    ]


__all__ = ["PATH_REPAIR_ACTION", "friendly_line", "steps", "shell_change_lines"]
