"""Existing-project lookup error, stale-link and bounded-history recovery views."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Protocol

from yoke_cli.config import onboard_existing_project
from yoke_cli.config.onboard_wizard_widgets import STEP_PROJECT
from yoke_cli.config.setup_prompt import TONE_ERROR, SelectionRow, SetupPrompt


if TYPE_CHECKING:  # pragma: no cover - typing only
    from yoke_cli.config.onboard_wizard_state import _View


class _Shell(Protocol):  # pragma: no cover - structural typing only
    _history: list[Any]
    result: Any

    def _goto(self, view: "_View") -> None: ...
    def _step_back(self) -> None: ...


class ExistingProjectLookupRecoveryFlow:
    def _goto_existing_project_lookup_error(
        self: _Shell,
        exc: BaseException,
        *,
        retry: Callable[[], None],
        local_destination: bool = False,
    ) -> None:
        from yoke_cli.config.onboard_wizard_state import _View

        rows = [
            SelectionRow("retry", "Try again", "rerun the project check"),
            SelectionRow("back", "Back", "previous screen"),
        ]
        hint = onboard_existing_project.lookup_error_hint(
            local_destination=local_destination,
        )
        self._goto(
            _View(
                SetupPrompt(
                    key="project.existing_project_lookup_error",
                    step=STEP_PROJECT,
                    title="Can't use that Yoke project.",
                    message=str(exc),
                    detail_lines=tuple([hint]),
                    choices=tuple(rows),
                    tone=TONE_ERROR,
                ),
                lambda choice: self._on_existing_project_lookup_error(
                    choice,
                    retry=retry,
                ),
            )
        )

    def _goto_stale_project_link(
        self: _Shell,
        exc: BaseException,
        local_ref: Any,
        *,
        retry: Callable[[], None],
        unlink: Callable[[], None],
    ) -> None:
        from yoke_cli.config.onboard_wizard_state import _View

        title, lines = onboard_existing_project.stale_link_copy(
            self.result, exc, local_ref
        )
        rows = [
            SelectionRow(
                "unlink",
                "Unlink and set up fresh",
                "set this folder up as a new project; Apply replaces the old link",
            ),
            SelectionRow("retry", "Try again", "rerun the project check"),
            SelectionRow("back", "Back", "previous screen"),
        ]

        def choose(choice: str) -> None:
            if choice == "unlink":
                unlink()
                return
            self._on_existing_project_lookup_error(choice, retry=retry)

        self._goto(
            _View(
                SetupPrompt(
                    key="project.stale_project_link",
                    step=STEP_PROJECT,
                    title=title,
                    message=str(exc),
                    detail_lines=tuple(lines),
                    choices=tuple(rows),
                    tone=TONE_ERROR,
                ),
                choose,
            )
        )

    def _on_existing_project_lookup_error(
        self: _Shell,
        choice: str,
        *,
        retry: Callable[[], None],
    ) -> None:
        if choice == "retry":
            if self._history:
                self._history.pop()
            retry()
            return
        self._step_back()


__all__ = ["ExistingProjectLookupRecoveryFlow"]
