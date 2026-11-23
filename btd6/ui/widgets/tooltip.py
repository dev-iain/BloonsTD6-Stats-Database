from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from btd6.ui.constants import SPACE_SM, SPACE_XS

TOOLTIP_OFFSET_PX = 16


class TooltipWindow:
    """A borderless label near the pointer; supplements, never replaces, visible text."""

    def __init__(self, owner: tk.Misc) -> None:
        self._owner = owner
        self._window: tk.Toplevel | None = None

    def show(self, text: str, root_x: int, root_y: int) -> None:
        self.hide()
        window = tk.Toplevel(self._owner)
        window.wm_overrideredirect(True)
        window.wm_geometry(f"+{root_x + TOOLTIP_OFFSET_PX}+{root_y + TOOLTIP_OFFSET_PX}")
        ttk.Label(window, text=text, style="Tooltip.TLabel", padding=(SPACE_SM, SPACE_XS)).pack()
        self._window = window

    def hide(self) -> None:
        if self._window is not None:
            self._window.destroy()
            self._window = None

    @property
    def visible(self) -> bool:
        return self._window is not None
