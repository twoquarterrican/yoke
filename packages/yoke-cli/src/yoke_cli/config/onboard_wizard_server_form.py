"""The team-server connection form: server URL, token source and credential."""

from __future__ import annotations

from textual.widgets import Input, Static

from yoke_cli.config.onboard_wizard_flow_protocols import ConnectFlowShell as _Shell
from yoke_cli.config.onboard_wizard_input_entry import form_field_widgets
from yoke_cli.config.onboard_wizard_palette import BRAND
from yoke_cli.config.onboard_wizard_self_host import NO_SERVER_GUIDANCE
from yoke_cli.config.onboard_wizard_widgets import STEP_CONNECT, SelectionList
from yoke_cli.config.setup_prompt import SelectionRow, SetupField, SetupPrompt
from yoke_cli.config.setup_prompt_render import heading

SERVER_TOKEN_SOURCE_ROWS = (
    SelectionRow("paste", "Paste token", "saved owner-only on this machine"),
    SelectionRow("file", "Token file", "read from an existing path"),
)
SERVER_FORM_AGENT_GUIDANCE = (
    "Answer the token source first. A pasted token is a secret: choose file and "
    "give the token file path, or ask the person to finish this step in the "
    "wizard with `yoke setup --tui`."
)


class ServerConnectionForm:
    def _goto_server_connection_form(self: _Shell) -> None:
        self._goto(self._server_connection_view())

    def _server_connection_view(self: _Shell):
        from yoke_cli.config.onboard_wizard_state import _View

        values = getattr(self, "_server_connection_values", {})
        source = getattr(self, "_server_token_source", "paste")
        fields = (
            SetupField(
                "server_url",
                "Server URL",
                "https://api.mycompany.com",
                validate=_validate_server_url,
                initial_value=str(
                    values.get("server_url") or self.result.api_url or ""
                ),
            ),
            SetupField(
                "credential",
                "API token" if source == "paste" else "Token file path",
                "paste token" if source == "paste" else "~/.yoke/secrets/team.token",
                password=True,
                initial_value=str(values.get("credential") or ""),
                secret=source == "paste",
            ),
        )
        prompt = SetupPrompt(
            key="connect.server",
            step=STEP_CONNECT,
            title=f"Connect to your {BRAND} team server.",
            subtitle="Enter the server and choose exactly where its token comes from.",
            detail_lines=(NO_SERVER_GUIDANCE,),
            choices=SERVER_TOKEN_SOURCE_ROWS,
            fields=fields,
            initial=0 if source == "paste" else 1,
            selected=source,
            guidance=SERVER_FORM_AGENT_GUIDANCE,
        )

        def builder() -> list[Static]:
            self._begin_form(fields, on_done=self._after_server_connection_form)
            return [
                *heading(prompt.title, prompt.subtitle)[:2],
                Static(NO_SERVER_GUIDANCE, classes="onboard-plan-line"),
                *form_field_widgets(fields[:1]),
                Static("  Token source", classes="onboard-plan-line"),
                SelectionList(list(prompt.choices), initial=prompt.initial),
                *form_field_widgets(fields[1:]),
            ]

        return _View(
            prompt,
            self._on_server_token_source,
            builder,
            on_form=self._after_server_connection_form,
        )

    def _on_server_token_source(self: _Shell, choice: str) -> None:
        if choice not in {"paste", "file"}:
            return
        values = {}
        for key in ("server_url", "credential"):
            try:
                values[key] = self.query_one(f"#onboard-input-{key}", Input).value
            except Exception:
                values[key] = ""
        self._server_connection_values = values
        self._server_token_source = choice
        self._replace_current(self._server_connection_view())
        try:
            self.set_focus(self.query_one("#onboard-input-credential", Input))
        except Exception:
            pass

    def _after_server_connection_form(self: _Shell, values: dict[str, str]) -> None:
        self._server_connection_values = dict(values)
        self.result.api_url = values["server_url"]
        source = getattr(self, "_server_token_source", "paste")
        credential = values["credential"]
        self._verify_yoke_token_value(
            token=credential if source == "paste" else None,
            token_file=credential if source == "file" else None,
            token_source_kind="prompt" if source == "paste" else "token_file",
            retry_source="server-form",
            replace_current=True,
        )


def _validate_server_url(value: str) -> str | None:
    from urllib.parse import urlsplit

    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "Enter a complete http:// or https:// server URL."
    return None


__all__ = ["SERVER_TOKEN_SOURCE_ROWS", "ServerConnectionForm"]
