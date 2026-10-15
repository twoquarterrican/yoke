"""Render a :class:`SetupPrompt` into the wizard's standard screen bodies.

Selection, typed-input, verification-result and checking screens all draw from
the prompt the screen declares, so each title, row and message has one source
that the agent-mode response reads too. Screens with a bespoke layout keep
their own builder and still declare a prompt.
"""

from __future__ import annotations

from rich.markup import escape
from textual.widgets import Static

from yoke_cli.config.onboard_wizard_palette import ACCENT
from yoke_cli.config.onboard_wizard_widgets import (
    FocusInput,
    SelectionList,
)
from yoke_cli.config.setup_prompt import SelectionRow
from yoke_cli.config.setup_prompt import TONE_ERROR, TONE_OK, SetupPrompt


def heading(title: str, subtitle: str | None) -> list[Static]:
    widgets = [Static(title, classes="onboard-title")]
    if subtitle is not None:
        widgets.append(Static(subtitle, classes="onboard-subtitle"))
    widgets.append(Static("", classes="onboard-spacer"))
    return widgets


def selection_body(
    title: str,
    subtitle: str | None,
    rows: list[SelectionRow],
    *,
    initial: int = 0,
) -> list[Static]:
    return [*heading(title, subtitle), SelectionList(list(rows), initial=initial)]


def input_body(
    title: str,
    subtitle: str,
    placeholder: str,
    password: bool,
    *,
    initial_value: str = "",
) -> list[Static]:
    return [
        *heading(title, subtitle),
        FocusInput(
            value=initial_value,
            placeholder=placeholder,
            password=password,
            id="onboard-input",
            classes="onboard-input",
        ),
        Static("", classes="onboard-input-error"),
    ]


def checking_body(
    title: str,
    message: str,
    detail_lines: list[str] | None = None,
) -> list[Static]:
    widgets = [
        Static(title, classes="onboard-title"),
        Static("", classes="onboard-spacer"),
        Static(escape(message), classes="onboard-plan-line"),
    ]
    widgets.extend(
        Static(f"  • {escape(line)}", classes="onboard-plan-line")
        for line in detail_lines or []
    )
    widgets.append(Static("", classes="onboard-spacer"))
    widgets.append(Static("Checking...", classes="onboard-note"))
    return widgets


def verification_body(
    title: str,
    message: str,
    detail_lines: list[str],
    rows: list[SelectionRow],
    *,
    ok: bool,
) -> list[Static]:
    if ok:
        widgets = [
            Static(title, classes="onboard-title"),
            Static("", classes="onboard-spacer"),
            Static(f"[{ACCENT}]{escape(message)}[/]", classes="onboard-plan-line"),
        ]
    else:
        widgets = [
            Static(f"✗ {escape(title)}", classes="onboard-title-error"),
            Static("", classes="onboard-spacer"),
            Static(f"Cause: {escape(message)}", classes="onboard-plan-line"),
            Static("What to do", classes="onboard-title"),
        ]
    widgets.extend(
        Static(f"  • {escape(line)}", classes="onboard-plan-line")
        for line in detail_lines
    )
    widgets.append(Static("", classes="onboard-spacer"))
    widgets.append(SelectionList(list(rows)))
    return widgets


def render(prompt: SetupPrompt) -> list[Static]:
    """The standard body for ``prompt``, chosen by what it asks."""
    if prompt.tone in (TONE_OK, TONE_ERROR):
        return verification_body(
            prompt.title,
            prompt.message or "",
            list(prompt.detail_lines),
            list(prompt.choices),
            ok=prompt.tone == TONE_OK,
        )
    if prompt.input is not None:
        return input_body(
            prompt.title,
            prompt.subtitle or "",
            prompt.input.placeholder,
            prompt.input.password,
            initial_value=prompt.input.initial_value,
        )
    if prompt.choices:
        return selection_body(
            prompt.title,
            prompt.subtitle,
            list(prompt.choices),
            initial=prompt.initial,
        )
    return checking_body(prompt.title, prompt.message or "", list(prompt.detail_lines))


__all__ = [
    "checking_body",
    "heading",
    "input_body",
    "render",
    "selection_body",
    "verification_body",
]
