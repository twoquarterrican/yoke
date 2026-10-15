"""Selection and single-input view constructors shared by every setup flow."""

from __future__ import annotations

from typing import Protocol

from textual.widgets import Static

from yoke_cli.config.onboard_wizard_state import _PendingInput, _View
from yoke_cli.config.setup_prompt import SetupInput, SetupPrompt
from yoke_cli.config.setup_prompt_render import render


class _Shell(Protocol):  # pragma: no cover - structural typing only
    _pending_input: _PendingInput | None

    def _goto(self, view: _View) -> None: ...


class ViewHelpers:
    def _selection_view(self: _Shell, key, step, title, subtitle, rows, on_select,
                        *, initial: int = 0, guidance: str = "") -> _View:
        return _View(
            SetupPrompt(
                key=key,
                step=step,
                title=title,
                subtitle=subtitle,
                choices=tuple(rows),
                initial=initial,
                guidance=guidance,
            ),
            on_select,
        )

    def _input_view(
        self: _Shell, key, step, title, subtitle, *, placeholder, on_done,
        password=False, allow_placeholder=True, validate=None,
        initial_value: str = "", guidance: str = "",
    ) -> _View:
        prompt = SetupPrompt(
            key=key,
            step=step,
            title=title,
            subtitle=subtitle,
            input=SetupInput(
                placeholder=placeholder,
                password=password,
                allow_placeholder=allow_placeholder,
                validate=validate,
                initial_value=initial_value,
            ),
            guidance=guidance,
        )

        def builder() -> list[Static]:
            self._pending_input = _PendingInput(
                on_done=on_done,
                placeholder=placeholder,
                allow_placeholder=allow_placeholder,
                validate=validate,
            )
            return render(prompt)

        return _View(prompt, on_done, builder)

    def _goto_input(self: _Shell, key, step, title, subtitle, *, placeholder, on_done,
                    password=False, allow_placeholder=True, validate=None,
                    initial_value: str = "", guidance: str = "") -> None:
        self._goto(self._input_view(
            key, step, title, subtitle, placeholder=placeholder,
            on_done=on_done, password=password,
            allow_placeholder=allow_placeholder, validate=validate,
            initial_value=initial_value, guidance=guidance,
        ))


__all__ = ["ViewHelpers"]
