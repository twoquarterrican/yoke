"""Prompts, option rows and the credential body for the wizard's Hosting step.

Provider choice and AWS sign-in choice are deliberately separate. Credential
entry then shares one field pair, custody explanation, verification action,
and outcome regardless of whether Yoke guided creation or the operator brought
an existing access key.
"""

from __future__ import annotations

from rich.markup import escape
from textual.widgets import Static

from yoke_cli.config import onboard_input_validation as input_validation
from yoke_cli.config.onboard_wizard_input_entry import form_field_widgets
from yoke_cli.config.onboard_wizard_palette import ACCENT
from yoke_cli.config.onboard_wizard_step_ids import STEP_HOSTING
from yoke_cli.config.setup_prompt import (
    TONE_ERROR,
    SelectionRow,
    SetupField,
    SetupHuman,
    SetupPrompt,
)
from yoke_cli.config.onboard_wizard_widgets import SelectionList

HOSTING_PROVIDER_TITLE = "Connect your hosting provider?"
HOSTING_PROVIDER_SUBTITLE = (
    "AWS is the one Yoke can run for you; hosting it yourself is a fine answer."
)
HOSTING_PROVIDER_ROWS = [
    SelectionRow("aws", "AWS", "Yoke can manage its infrastructure"),
    SelectionRow(
        "no-managed-host",
        "I host this myself",
        "Yoke applies no infrastructure",
    ),
    SelectionRow("skip", "Decide later", "/yoke onboard asks again"),
]

HOSTING_AWS_SIGN_IN_TITLE = "How should Yoke sign in to AWS?"
HOSTING_AWS_SIGN_IN_SUBTITLE = "Choose an access-key path Yoke can execute today."
HOSTING_AWS_SIGN_IN_ROWS = [
    SelectionRow(
        "create-key",
        "Create a dedicated deploy key",
        "Recommended",
    ),
    SelectionRow(
        "existing-key",
        "Use existing credentials",
        "An access key you manage",
    ),
    SelectionRow("skip", "Not now", "Continue without AWS credentials"),
]

HOSTING_ACCESS_KEY_FIELD = SetupField(
    key="access-key-id",
    label="Access key ID",
    placeholder="AKIA...",
    validate=input_validation.validate_access_key_id,
)
HOSTING_SECRET_KEY_FIELD = SetupField(
    key="secret-access-key",
    label="Secret access key",
    placeholder="the secret value from the stack",
    password=True,
    validate=input_validation.validate_secret_access_key,
)
HOSTING_CREDENTIAL_FIELDS = (HOSTING_ACCESS_KEY_FIELD, HOSTING_SECRET_KEY_FIELD)

HOSTING_CREDENTIAL_ROWS = [
    SelectionRow("connect", "Save & verify", "Confirm the AWS identity"),
    SelectionRow("skip", "Not now", "Continue without AWS credentials"),
]
HOSTING_RETRY_ROWS = [
    SelectionRow("retry", "Re-enter the two values", "paste them again"),
    SelectionRow("skip", "Not now", "Continue without AWS credentials"),
]

HOSTING_GUIDED_KEY_TITLE = "Create a dedicated deploy key"
HOSTING_GUIDED_KEY_SUBTITLE = (
    "New to AWS? Create an account at aws.amazon.com first, then return here."
)
HOSTING_EXISTING_KEY_TITLE = "Use existing credentials"
HOSTING_EXISTING_KEY_SUBTITLE = (
    "Paste an access key pair from an AWS identity your team already manages."
)

# Fallback for a source build or a channel without an allowlisted regional S3
# template origin. CloudFormation rejects custom distribution and website hosts.
NO_LINK_RECOVERY_LINE = (
    "Reinstall from a hosted Yoke release, or go back and use existing credentials."
)


HOSTING_AGENT_GUIDANCE = (
    "Ask the person which answer fits. AWS access keys are secrets: the person "
    "enters them in the wizard (`yoke setup --tui`), never in chat."
)

HOSTING_PROVIDER_PROMPT = SetupPrompt(
    key="hosting.provider",
    step=STEP_HOSTING,
    title=HOSTING_PROVIDER_TITLE,
    subtitle=HOSTING_PROVIDER_SUBTITLE,
    choices=tuple(HOSTING_PROVIDER_ROWS),
    guidance=HOSTING_AGENT_GUIDANCE,
)
HOSTING_AWS_SIGN_IN_PROMPT = SetupPrompt(
    key="hosting.aws_sign_in",
    step=STEP_HOSTING,
    title=HOSTING_AWS_SIGN_IN_TITLE,
    subtitle=HOSTING_AWS_SIGN_IN_SUBTITLE,
    choices=tuple(HOSTING_AWS_SIGN_IN_ROWS),
    guidance=HOSTING_AGENT_GUIDANCE,
)


def hosting_credentials_prompt(
    *,
    guided: bool,
    quick_create_url: str | None,
    credential_dir: str,
) -> SetupPrompt:
    """Credential entry, with the one-click dedicated-key route when guided."""
    return SetupPrompt(
        key="hosting.aws_credentials",
        step=STEP_HOSTING,
        title=HOSTING_GUIDED_KEY_TITLE if guided else HOSTING_EXISTING_KEY_TITLE,
        subtitle=HOSTING_GUIDED_KEY_SUBTITLE if guided else HOSTING_EXISTING_KEY_SUBTITLE,
        detail_lines=(f"The key stays on this machine ({credential_dir}).",),
        choices=tuple(HOSTING_CREDENTIAL_ROWS),
        fields=HOSTING_CREDENTIAL_FIELDS,
        selected="connect",
        human=SetupHuman(
            "Open the AWS setup page and create the deploy key; then enter "
            "both values in the wizard.",
            url=quick_create_url,
        ) if guided and quick_create_url else None,
        guidance=HOSTING_AGENT_GUIDANCE,
    )


def hosting_error_prompt(title: str, message: str, details: list[str]) -> SetupPrompt:
    """The plain cause and every required recovery action."""
    return SetupPrompt(
        key="hosting.aws_error",
        step=STEP_HOSTING,
        title=title,
        message=message,
        detail_lines=tuple(details),
        choices=tuple(HOSTING_RETRY_ROWS),
        tone=TONE_ERROR,
    )


def hosting_credential_body(
    prompt: SetupPrompt,
    *,
    guided: bool,
    credential_dir: str,
) -> list[Static]:
    creation_link = None
    if guided:
        creation_link = prompt.human.url if prompt.human else NO_LINK_RECOVERY_LINE
    return _hosting_credential_body(
        title=prompt.title,
        subtitle=prompt.subtitle or "",
        credential_dir=credential_dir,
        creation_link=creation_link,
    )


def _hosting_credential_body(
    *,
    title: str,
    subtitle: str,
    credential_dir: str,
    creation_link: str | None,
) -> list[Static]:
    widgets: list[Static] = [
        Static(title, classes="onboard-title"),
        Static(subtitle, classes="onboard-subtitle"),
        Static("", classes="onboard-spacer"),
    ]
    if creation_link is not None:
        if creation_link == NO_LINK_RECOVERY_LINE:
            widgets.append(Static(creation_link, classes="onboard-plan-line"))
        else:
            widgets.extend(
                [
                    Static(
                        f"[{ACCENT}]Open AWS setup page[/]",
                        classes="onboard-title",
                    ),
                    Static(
                        "Ctrl+O opens it in your browser. Ctrl+Y copies the URL.",
                        classes="onboard-plan-line",
                    ),
                    Static(
                        f"URL: {escape(creation_link)}",
                        classes="onboard-plan-line",
                    ),
                    Static("", classes="onboard-spacer"),
                    Static(
                        "Then paste the two values here — never into an AI chat:",
                        classes="onboard-plan-line",
                    ),
                ]
            )
    else:
        widgets.append(
            Static(
                "  Paste the two values here — never into an AI chat:",
                classes="onboard-plan-line",
            )
        )
    widgets.extend(
        [
            *form_field_widgets(HOSTING_CREDENTIAL_FIELDS),
            Static(
                f"  Stays on this machine ({escape(credential_dir)}) —",
                classes="onboard-subtitle",
            ),
            Static(
                "  operator-attended; CI only ever gets scoped OIDC roles minted later.",
                classes="onboard-subtitle",
            ),
            Static("", classes="onboard-spacer"),
            SelectionList(HOSTING_CREDENTIAL_ROWS),
        ]
    )
    return widgets


__all__ = [
    "HOSTING_ACCESS_KEY_FIELD",
    "HOSTING_AWS_SIGN_IN_ROWS",
    "HOSTING_AWS_SIGN_IN_SUBTITLE",
    "HOSTING_AWS_SIGN_IN_TITLE",
    "HOSTING_CREDENTIAL_FIELDS",
    "HOSTING_CREDENTIAL_ROWS",
    "HOSTING_EXISTING_KEY_SUBTITLE",
    "HOSTING_EXISTING_KEY_TITLE",
    "HOSTING_GUIDED_KEY_SUBTITLE",
    "HOSTING_GUIDED_KEY_TITLE",
    "HOSTING_PROVIDER_ROWS",
    "HOSTING_PROVIDER_SUBTITLE",
    "HOSTING_PROVIDER_TITLE",
    "HOSTING_RETRY_ROWS",
    "HOSTING_SECRET_KEY_FIELD",
    "NO_LINK_RECOVERY_LINE",
    "HOSTING_AGENT_GUIDANCE",
    "HOSTING_AWS_SIGN_IN_PROMPT",
    "HOSTING_PROVIDER_PROMPT",
    "hosting_credential_body",
    "hosting_credentials_prompt",
    "hosting_error_prompt",
]
