"""Checking an agent's answer against the screen it answers, then applying it.

Each answer goes through the same rules the wizard's own controls enforce: a
choice must be one of the screen's rows, a typed value runs the screen's own
validation and default, and a form takes ``<key>.<field>`` values. Secret
inputs never accept an answer. A rejected answer raises
:class:`SetupRefusal` before anything runs, so a refusal changes nothing.
"""

from __future__ import annotations

from typing import Any

from yoke_cli.config import onboard_wizard_apply_prompts as apply_prompts
from yoke_cli.config.onboard_wizard_state import _View
from yoke_cli.config.setup_prompt import (
    SetupPrompt,
    check_choice,
    check_field,
    check_input,
)

REVIEW_KEY = "review.confirm"
# Answers that run or redirect Apply count only in the invocation that gives
# them, so replaying stored answers never starts Apply on its own.
INVOCATION_ONLY_KEYS = frozenset({
    REVIEW_KEY,
    apply_prompts.APPLY_FAILED_KEY,
    apply_prompts.APPLY_DIFFERENT_FOLDER_KEY,
})


class SetupRefusal(Exception):
    """A named refusal plus its recovery, raised at the screen it concerns."""

    def __init__(self, reason: str, recovery: str, prompt: SetupPrompt | None) -> None:
        super().__init__(recovery)
        self.reason = reason
        self.recovery = recovery
        self.prompt = prompt


class AnswerFlow:
    """Validate and apply one screen's answers; stage them for the store."""

    def _cli_for(self, key: str) -> dict[str, str]:
        prefix = f"{key}."
        return {
            name: value
            for name, value in self._cli.items()
            if name == key or name.startswith(prefix)
        }

    def _answer(self, view: _View, values: dict[str, str]) -> None:
        prompt = view.prompt
        if prompt.input is not None:
            self._answer_input(view, values)
        elif prompt.fields:
            self._answer_form(view, values)
        else:
            self._answer_choice(view, values)

    def _answer_input(self, view: _View, values: dict[str, str]) -> None:
        prompt = view.prompt
        value = values.get(prompt.key)
        if value is None:
            raise _not_current(prompt)
        if prompt.input.password:
            raise _secret(prompt)
        text, error = check_input(prompt.input, value)
        if error:
            raise SetupRefusal("setup_answer_invalid", error, prompt)
        self._accept(prompt, {prompt.key: text}, used=[prompt.key])
        view.on_select(text)

    def _answer_choice(self, view: _View, values: dict[str, str]) -> None:
        prompt = view.prompt
        value = values.get(prompt.key)
        if value is None:
            raise _not_current(prompt)
        error = check_choice(prompt, value)
        if error:
            raise SetupRefusal("setup_answer_not_allowed", error, prompt)
        self._accept(prompt, {prompt.key: value}, used=[prompt.key])
        view.on_select(value)

    def _answer_form(self, view: _View, values: dict[str, str]) -> None:
        prompt = view.prompt
        choice = values.get(prompt.key)
        if choice is not None:
            error = check_choice(prompt, choice)
            if error:
                raise SetupRefusal("setup_answer_not_allowed", error, prompt)
            if prompt.selected is not None and choice != prompt.selected:
                # Switching the screen's mode redraws it; the field answers
                # wait for the redrawn screen.
                self._accept(prompt, {prompt.key: choice}, used=[prompt.key])
                view.on_select(choice)
                return
        submitted: dict[str, str] = {}
        for field in prompt.fields:
            name = f"{prompt.key}.{field.key}"
            if field.is_secret:
                raise _secret(prompt)
            text, error = check_field(field, values.get(name, ""))
            if error:
                raise SetupRefusal("setup_answer_invalid", f"{name}: {error}", prompt)
            submitted[field.key] = text
        staged = {f"{prompt.key}.{name}": text for name, text in submitted.items()}
        if choice is not None:
            staged[prompt.key] = choice
        self._accept(prompt, staged, used=[prompt.key, *staged])
        view.on_form(submitted)

    def _accept(self, prompt: SetupPrompt, staged: dict[str, str], *, used: list[str]) -> None:
        for name in used:
            self._cli.pop(name, None)
        if prompt.key == apply_prompts.APPLY_FAILED_KEY:
            self._answers.apply_failure = None
        if prompt.key not in INVOCATION_ONLY_KEYS:
            self._answers.stage(staged)

    def _done_fields(self) -> dict[str, Any]:
        report = getattr(self, "_applied_report", None)
        report = report if isinstance(report, dict) else {}
        summary = report.get("apply_report")
        changed = list((self.result.path_repair or {}).get("changed_files") or [])
        checkout = self.result.project_checkout
        next_steps = []
        if changed:
            next_steps.append(
                "Open a new terminal so the changed shell files take effect: "
                + ", ".join(changed)
            )
        if checkout:
            next_steps.append(f"Open Claude Code, Codex or Cursor in {checkout}.")
            next_steps.append("Run /yoke onboard in that session.")
        else:
            next_steps.append(
                "To add a project later, run `yoke setup --agent` again and "
                "choose the folder its code lives in."
            )
        return {
            "detail": [f"Run report: {self.report_path}"] if self.report_path else [],
            "report": summary if isinstance(summary, dict) else None,
            "install_health": report.get("install_health"),
            "changed_files": changed,
            "next": next_steps,
            "guidance": (
                "Tell the person setup is done, show the install health result in "
                "full, and give them the next steps in order. Yoke never opens "
                "that session for them."
            ),
        }


def _secret(prompt: SetupPrompt) -> SetupRefusal:
    return SetupRefusal(
        "setup_secret_answer_refused",
        "setup never takes a secret through --answer; take this question's "
        "non-secret route, or finish this step in a terminal with `yoke setup --tui`",
        prompt,
    )


def _not_current(prompt: SetupPrompt) -> SetupRefusal:
    return SetupRefusal(
        "setup_answer_not_current",
        f"answer {prompt.key} itself; its field answers alone do not answer it",
        prompt,
    )


__all__ = ["AnswerFlow", "INVOCATION_ONLY_KEYS", "REVIEW_KEY", "SetupRefusal"]
