from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import dataclass
from tkinter import font as tkfont
from tkinter import ttk

from btd6.ui.constants import (
    CAPTION_SIZE_DELTA,
    HEADING_SIZE_DELTA,
    MIN_BASE_FONT_PT,
    MIN_TARGET_PX,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
)
from btd6.ui.palettes import Palette

REFERENCE_SCALING = 96 / 72


@dataclass(frozen=True)
class Fonts:
    body: tkfont.Font
    heading: tkfont.Font
    caption: tkfont.Font
    monospace: tkfont.Font


def enable_dpi_awareness() -> None:
    """Ask Windows for per-monitor DPI awareness; a no-op everywhere else."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except AttributeError, OSError:
        pass


def base_font_size(default_font: tkfont.Font) -> int:
    size = int(default_font.actual("size"))
    return max(MIN_BASE_FONT_PT, size if size > 0 else MIN_BASE_FONT_PT)


def build_fonts(root: tk.Misc) -> Fonts:
    default = tkfont.nametofont("TkDefaultFont", root=root)
    fixed = tkfont.nametofont("TkFixedFont", root=root)
    base = base_font_size(default)
    family = default.actual("family")
    return Fonts(
        body=tkfont.Font(root=root, family=family, size=base),
        heading=tkfont.Font(
            root=root, family=family, size=base + HEADING_SIZE_DELTA, weight="bold"
        ),
        caption=tkfont.Font(root=root, family=family, size=base + CAPTION_SIZE_DELTA),
        monospace=tkfont.Font(root=root, family=fixed.actual("family"), size=base),
    )


def scale_factor(root: tk.Misc) -> float:
    return float(root.tk.call("tk", "scaling")) / REFERENCE_SCALING


def row_height(root: tk.Misc, fonts: Fonts) -> int:
    content = fonts.monospace.metrics("linespace") + SPACE_SM
    return max(content, round(MIN_TARGET_PX * scale_factor(root)))


def configure_base(style: ttk.Style, palette: Palette, fonts: Fonts) -> None:
    style.theme_use("clam")
    style.configure(
        ".",
        background=palette.color_background,
        foreground=palette.color_text,
        font=fonts.body,
        bordercolor=palette.color_border,
        focuscolor=palette.color_focus,
        troughcolor=palette.color_surface_alt,
    )
    style.configure("TFrame", background=palette.color_background)
    style.configure("TLabel", background=palette.color_background, foreground=palette.color_text)
    style.map("TLabel", foreground=[("disabled", palette.color_text_disabled)])


def configure_labels(style: ttk.Style, palette: Palette, fonts: Fonts) -> None:
    style.configure("Muted.TLabel", foreground=palette.color_text_muted, font=fonts.caption)
    style.configure("Heading.TLabel", font=fonts.heading)
    style.configure("Error.TLabel", foreground=palette.color_danger, font=fonts.caption)
    style.configure("Status.TLabel", foreground=palette.color_text, padding=(0, SPACE_XS))
    style.configure("StatusError.TLabel", foreground=palette.color_danger, padding=(0, SPACE_XS))
    style.configure(
        "Placeholder.TLabel",
        background=palette.color_surface,
        foreground=palette.color_text_muted,
        font=fonts.heading,
    )
    style.configure(
        "Tooltip.TLabel",
        background=palette.color_surface_alt,
        foreground=palette.color_text,
        bordercolor=palette.color_border,
        relief="solid",
        borderwidth=1,
    )
    style.configure("Placeholder.TFrame", background=palette.color_surface)


def configure_button(
    style: ttk.Style, palette: Palette, name: str, colors: tuple[str, str, str, str]
) -> None:
    base, hover, pressed, text = colors
    style.configure(
        name,
        background=base,
        foreground=text,
        padding=(SPACE_MD, SPACE_SM),
        bordercolor=palette.color_border,
    )
    focus = [("focus", palette.color_focus)]
    style.map(
        name,
        background=[
            ("disabled", palette.color_surface_alt),
            ("pressed", pressed),
            ("active", hover),
        ],
        foreground=[("disabled", palette.color_text_disabled), ("!disabled", text)],
        bordercolor=focus,
        lightcolor=focus,
        darkcolor=focus,
    )


def configure_buttons(style: ttk.Style, palette: Palette) -> None:
    configure_button(
        style,
        palette,
        "Action.TButton",
        (
            palette.color_accent,
            palette.color_accent_hover,
            palette.color_accent_pressed,
            palette.color_on_accent,
        ),
    )
    configure_button(
        style,
        palette,
        "Secondary.TButton",
        (
            palette.color_button,
            palette.color_button_hover,
            palette.color_button_pressed,
            palette.color_text,
        ),
    )


def configure_inputs(style: ttk.Style, palette: Palette) -> None:
    style.configure(
        "Filter.TEntry",
        fieldbackground=palette.color_surface,
        foreground=palette.color_text,
        insertcolor=palette.color_text,
        padding=SPACE_SM,
    )
    style.map(
        "Filter.TEntry",
        bordercolor=[("invalid", palette.color_danger), ("focus", palette.color_focus)],
        lightcolor=[("invalid", palette.color_danger), ("focus", palette.color_focus)],
        darkcolor=[("invalid", palette.color_danger), ("focus", palette.color_focus)],
        fieldbackground=[("disabled", palette.color_surface_alt)],
        foreground=[("disabled", palette.color_text_disabled)],
    )
    for name in ("Filter.TRadiobutton", "Filter.TCheckbutton", "Toolbar.TCheckbutton"):
        style.configure(name, background=palette.color_background, foreground=palette.color_text)
        style.map(
            name,
            background=[("active", palette.color_surface_alt)],
            foreground=[("disabled", palette.color_text_disabled)],
            indicatorcolor=[
                ("selected", palette.color_accent),
                ("!selected", palette.color_surface),
            ],
            focuscolor=[("focus", palette.color_focus)],
        )


def configure_scrollbars(style: ttk.Style, palette: Palette) -> None:
    for orient in ("Vertical", "Horizontal"):
        name = f"Stats.{orient}.TScrollbar"
        style.configure(
            name,
            background=palette.color_button,
            arrowcolor=palette.color_text,
            bordercolor=palette.color_border,
        )
        style.map(
            name,
            background=[
                ("pressed", palette.color_button_pressed),
                ("active", palette.color_button_hover),
            ],
        )


def configure_containers(style: ttk.Style, palette: Palette, fonts: Fonts) -> None:
    style.configure(
        "Filter.TLabelframe",
        background=palette.color_background,
        bordercolor=palette.color_border,
        padding=SPACE_SM,
    )
    style.configure(
        "Filter.TLabelframe.Label",
        background=palette.color_background,
        foreground=palette.color_text,
        font=fonts.heading,
    )
    style.configure(
        "Status.Horizontal.TProgressbar",
        background=palette.color_accent,
        troughcolor=palette.color_surface_alt,
        bordercolor=palette.color_border,
    )
    configure_scrollbars(style, palette)


def configure_treeview(style: ttk.Style, palette: Palette, fonts: Fonts, height: int) -> None:
    style.configure(
        "Stats.Treeview",
        background=palette.color_surface,
        fieldbackground=palette.color_surface,
        foreground=palette.color_text,
        font=fonts.monospace,
        rowheight=height,
        bordercolor=palette.color_border,
    )
    style.map(
        "Stats.Treeview",
        background=[("selected", palette.color_selection)],
        foreground=[("selected", palette.color_on_selection)],
    )
    style.configure(
        "Stats.Treeview.Heading",
        background=palette.color_header,
        foreground=palette.color_text,
        font=fonts.heading,
        padding=(SPACE_SM, SPACE_SM),
        relief="flat",
    )
    style.map(
        "Stats.Treeview.Heading",
        background=[
            ("pressed", palette.color_button_pressed),
            ("active", palette.color_button_hover),
        ],
    )


def apply_theme(root: tk.Misc, palette: Palette, fonts: Fonts) -> None:
    style = ttk.Style(root)
    configure_base(style, palette, fonts)
    configure_labels(style, palette, fonts)
    configure_buttons(style, palette)
    configure_inputs(style, palette)
    configure_containers(style, palette, fonts)
    configure_treeview(style, palette, fonts, row_height(root, fonts))
    root.configure(background=palette.color_background)
