"""Install failure screen and shell-file change summary."""

from __future__ import annotations

from typing import Any

from rich.markup import escape
from textual.widgets import Static

from yoke_cli.config.onboard_path_plan import shell_change_lines
from yoke_cli.config.onboard_wizard_widgets import SelectionList
from yoke_cli.config.onboard_wizard_step_ids import STEP_INSTALL
from yoke_cli.config.setup_prompt import SelectionRow, SetupPrompt


def path_apply_error_prompt(
    message: str,
    plan: dict[str, Any] | None = None,
) -> SetupPrompt:
    return SetupPrompt(
        key="install.error",
        step=STEP_INSTALL,
        title="Install needs attention.",
        message=message,
        detail_lines=tuple(shell_change_lines(plan)),
        choices=(SelectionRow("retry", "Retry Install", "run the checks again"),),
        guidance="Fix the named cause on this machine, then answer retry.",
    )


def path_apply_error_body(prompt: SetupPrompt) -> list[Static]:
    return [
        Static(prompt.title, classes="onboard-title"),
        Static(escape(prompt.message or ""), classes="onboard-plan-line"),
        *(Static(escape(line), classes="onboard-plan-line") for line in prompt.detail_lines),
        Static("", classes="onboard-spacer"),
        SelectionList(list(prompt.choices)),
    ]


__all__ = ["path_apply_error_body", "path_apply_error_prompt", "shell_change_lines"]
