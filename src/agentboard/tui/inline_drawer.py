"""InlineDrawer — Cinema Labor progressive disclosure (M1b m_009-m_011).

Container widget that hosts at most one mounted "drawer" content widget
at a time. Opening a new drawer closes any existing one in the same
container scope. Closing restores focus to the widget that triggered
the open.

Design notes (per /autoplan Eng F1):
- Use `await mount()` so focus assertions in tests can pause and observe
  fully-mounted state.
- Dynamic mount avoids the Textual compose-once trap; each open is a
  fresh widget instance attached to the container.
- Track `triggering_widget` per open so close can restore focus exactly.
- One-at-a-time enforced by storing current `_active_id` and removing
  prior content before mounting new.
"""
from __future__ import annotations

from textual.containers import Vertical
from textual.widget import Widget


class DrawerContainer(Vertical):
    """Hosts at most one drawer content widget at a time."""

    DEFAULT_CSS = """
    DrawerContainer {
        height: auto;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._active: Widget | None = None
        self._trigger: Widget | None = None

    async def open(self, content_widget: Widget, *, trigger: Widget | None = None) -> None:
        """Mount `content_widget` as the active drawer.

        Closes any existing drawer first (one-at-a-time invariant).
        Stores `trigger` so close() can restore focus.
        """
        # Close existing without focus restore (the new content takes over)
        await self._remove_active()
        await self.mount(content_widget)
        self._active = content_widget
        self._trigger = trigger

    async def close(self) -> None:
        """Remove the active drawer and restore focus to its trigger."""
        await self._remove_active()
        if self._trigger is not None:
            try:
                self._trigger.focus()
            except Exception:
                pass
        self._trigger = None

    async def _remove_active(self) -> None:
        if self._active is None:
            return
        try:
            await self._active.remove()
        except Exception:
            pass
        self._active = None
