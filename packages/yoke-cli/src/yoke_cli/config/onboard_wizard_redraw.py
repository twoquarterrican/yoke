"""Erase-then-repaint frames for the full-screen setup wizard.

Textual normally paints only the regions that changed. A terminal can still
hold cells Textual no longer models: a resize crops or reflows the old frame,
and ``App._display`` silently drops any frame produced while updates are
batched, after which the compositor believes those cells were painted. The
wizard therefore turns the first frame after a resize, a view swap, or a
dropped frame into one write that erases the screen and repaints every cell,
inside the same synchronized-output block, so no glyph of an earlier view or
size survives beside the current one.

This hooks Textual's single frame funnel (``App._display``); the redraw tests
fail if a Textual upgrade stops routing frames through it.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from textual._compositor import CompositorUpdate, LayoutUpdate
from textual.geometry import Size

RESET_AND_ERASE_SCREEN = "\x1b[0m\x1b[2J"


class ErasedFullFrame(CompositorUpdate):
    """A full-screen frame preceded by an erase of the whole terminal."""

    def __init__(self, frame: LayoutUpdate) -> None:
        self.frame = frame

    def render_segments(self, console: Console) -> str:
        return RESET_AND_ERASE_SCREEN + self.frame.render_segments(console)


class FullFrameRedraw:
    """App mixin: erase and fully repaint after every resize and view swap."""

    _full_frame_due = True
    _painted_size: Size | None = None

    def _request_full_frame(self) -> None:
        self._full_frame_due = True
        self.refresh()  # type: ignore[attr-defined]

    def _end_batch(self) -> None:
        super()._end_batch()  # type: ignore[misc]
        if self._full_frame_due and not self._batch_count:  # type: ignore[attr-defined]
            # A frame dropped inside the batch leaves nothing dirty to repaint.
            self.refresh()  # type: ignore[attr-defined]

    def _display(self, screen: Any, renderable: Any) -> None:
        if isinstance(renderable, CompositorUpdate) and not self.is_inline:  # type: ignore[attr-defined]
            if self._batch_count:  # type: ignore[attr-defined]
                # Textual discards this frame; repaint everything next time.
                self._full_frame_due = True
            elif self._full_frame_due or screen.size != self._painted_size:
                frame = (
                    renderable
                    if isinstance(renderable, LayoutUpdate)
                    else screen._compositor.render_full_update()
                )
                renderable = ErasedFullFrame(frame)
                self._full_frame_due = False
                self._painted_size = screen.size
        super()._display(screen, renderable)  # type: ignore[misc]


__all__ = ["ErasedFullFrame", "FullFrameRedraw", "RESET_AND_ERASE_SCREEN"]
