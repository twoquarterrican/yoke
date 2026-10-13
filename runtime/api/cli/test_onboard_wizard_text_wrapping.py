"""Setup text reflows, including recovery commands and footer actions."""

import asyncio

import pytest
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static
from textual.geometry import Region

from yoke_cli.config import onboard_wizard_chrome as chrome
from yoke_cli.config.onboard_wizard_widgets import Stepper

LONG_COPY = "Use yoke github disconnect to remove this connection and try again."
LONG_TOKEN = "https://example.test/" + "approval" * 15


class WrappingApp(App):
    CSS_PATH = "../../../packages/yoke-cli/src/yoke_cli/config/onboard_wizard.tcss"

    def compose(self) -> ComposeResult:
        yield Static(chrome.header(), id="onboard-header")
        yield Stepper(id="onboard-stepper")
        with VerticalScroll(id="onboard-body"):
            for name in (
                "title",
                "subtitle",
                "note",
                "plan-line",
                "input-error",
                "search-status",
                "field-error",
            ):
                yield Static(LONG_COPY, classes=f"onboard-{name} -shown", id=name)
            yield Static(LONG_TOKEN, classes="onboard-plan-line", id="token")
        yield Static(
            chrome.footer(open_label="open the approval link"), id="onboard-footer"
        )


def rendered_text(widget):
    strips = widget.render_lines(
        Region(0, 0, widget.region.width, widget.region.height)
    )
    return "\n".join(strip.text for strip in strips)


@pytest.mark.parametrize("width", [40, 60, 80])
def test_text_and_footer_reflow_without_losing_words(width):
    app = WrappingApp()

    async def scenario():
        async with app.run_test(size=(width, 40)) as pilot:
            await pilot.pause()
            for name in (
                "title",
                "subtitle",
                "note",
                "plan-line",
                "input-error",
                "search-status",
                "field-error",
            ):
                widget = app.query_one(f"#{name}")
                assert widget.size.height >= 1
                if width <= 60:
                    assert widget.size.height > 1
                assert rendered_text(widget).split() == LONG_COPY.split()
            assert LONG_TOKEN in rendered_text(app.query_one("#token")).replace(
                " ", ""
            ).replace("\n", "")
            header = rendered_text(app.query_one("#onboard-header"))
            assert "projects" in header
            rail = rendered_text(app.query_one("#onboard-stepper"))
            assert "Review" in rail
            footer = app.query_one("#onboard-footer")
            assert "approval link" in " ".join(rendered_text(footer).split())
            assert footer.region.bottom <= 39
            assert app.query_one("#onboard-body").region.bottom <= footer.region.y
            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            assert app.query_one("#title").size.height == 1
            assert app.query_one("#onboard-footer").size.height == 1

    asyncio.run(scenario())
