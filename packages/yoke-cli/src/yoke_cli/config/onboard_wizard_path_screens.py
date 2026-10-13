"""Install failure screen and shell-file change summary."""

from __future__ import annotations

from typing import Any

from rich.markup import escape
from textual.widgets import Static

from yoke_cli.config.onboard_path_plan import shell_change_lines
from yoke_cli.config.onboard_wizard_widgets import SelectionList, SelectionRow


def path_apply_error_body(
    message: str,
    plan: dict[str, Any] | None = None,
) -> list[Static]:
    return [
        Static("Install needs attention.", classes="onboard-title"),
        Static(escape(message), classes="onboard-plan-line"),
        *(
            Static(escape(line), classes="onboard-plan-line")
            for line in shell_change_lines(plan)
        ),
        Static("", classes="onboard-spacer"),
        SelectionList([SelectionRow("retry", "Retry Install", "run the checks again")]),
    ]


__all__ = ["path_apply_error_body", "shell_change_lines"]
