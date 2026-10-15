"""Single prefilled project-details form used for new project identities."""

from __future__ import annotations

from textual.widgets import Static

from yoke_cli.config import onboard_input_validation as validation
from yoke_cli.config import onboard_project
from yoke_cli.config.onboard_wizard_input_entry import form_field_widgets
from yoke_cli.config.onboard_wizard_step_ids import STEP_PROJECT
from yoke_cli.config.setup_prompt import SelectionRow, SetupField, SetupPrompt
from yoke_cli.config.onboard_wizard_widgets import SelectionList


def fields(*, slug: str, branch_from_source: str | None) -> tuple[SetupField, ...]:
    items = [
        SetupField(
            "slug",
            "Project ID",
            "my-project",
            validate=validation.validate_slug,
            initial_value=slug,
        ),
        SetupField(
            "name",
            "Display name",
            "My Project",
            validate=validation.validate_display_name,
            initial_value=slug,
        ),
    ]
    if not branch_from_source:
        items.append(
            SetupField(
                "branch",
                "Default branch",
                onboard_project.DEFAULT_NEW_REPO_BRANCH,
                validate=validation.validate_branch,
                initial_value=onboard_project.DEFAULT_NEW_REPO_BRANCH,
            )
        )
    prefix = "".join(character for character in slug.upper() if character.isalnum())[:6]
    if len(prefix) < 2:
        prefix = "PRJ"
    items.append(
        SetupField(
            "prefix",
            "Item prefix",
            "PROJ",
            validate=validation.validate_prefix,
            initial_value=prefix,
        )
    )
    return tuple(items)


CONTINUE_ROWS = (
    SelectionRow("continue", "Continue", "validate and save these project details"),
)


def prompt(
    form_fields: tuple[SetupField, ...], *, branch_from_source: str | None
) -> SetupPrompt:
    return SetupPrompt(
        key="project.details",
        step=STEP_PROJECT,
        title="Project details.",
        subtitle="Enter advances fields; Enter on the last field validates the form.",
        detail_lines=(
            (f"Default branch: {branch_from_source} (from source repository)",)
            if branch_from_source
            else ()
        ),
        choices=CONTINUE_ROWS,
        fields=form_fields,
        selected="continue",
        guidance="Each field has a suggested value; answer only the ones the "
        "person wants changed, then answer continue.",
    )


def body(details: SetupPrompt) -> list[Static]:
    widgets: list[Static] = [
        Static(details.title, classes="onboard-title"),
        Static(details.subtitle or "", classes="onboard-subtitle"),
        *(Static(line, classes="onboard-plan-line") for line in details.detail_lines),
    ]
    widgets.extend(form_field_widgets(details.fields))
    widgets.append(SelectionList(list(details.choices)))
    return widgets


__all__ = ["CONTINUE_ROWS", "body", "fields", "prompt"]
