from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    name: str
    color_background: str
    color_surface: str
    color_surface_alt: str
    color_header: str
    color_text: str
    color_text_muted: str
    color_text_disabled: str
    color_border: str
    color_focus: str
    color_accent: str
    color_accent_hover: str
    color_accent_pressed: str
    color_on_accent: str
    color_selection: str
    color_on_selection: str
    color_danger: str
    color_button: str
    color_button_hover: str
    color_button_pressed: str


LIGHT = Palette(
    name="light",
    color_background="#eef1f5",
    color_surface="#ffffff",
    color_surface_alt="#f0f3f8",
    color_header="#dde3ec",
    color_text="#1a1d21",
    color_text_muted="#4a5360",
    color_text_disabled="#6b7280",
    color_border="#68717f",
    color_focus="#1d4ed8",
    color_accent="#1d4ed8",
    color_accent_hover="#1e40af",
    color_accent_pressed="#1e3a8a",
    color_on_accent="#ffffff",
    color_selection="#1d4ed8",
    color_on_selection="#ffffff",
    color_danger="#b42318",
    color_button="#dde3ec",
    color_button_hover="#cbd3df",
    color_button_pressed="#b9c3d2",
)

DARK = Palette(
    name="dark",
    color_background="#14181d",
    color_surface="#1c2128",
    color_surface_alt="#232a33",
    color_header="#2d3641",
    color_text="#e6e9ee",
    color_text_muted="#aab3bf",
    color_text_disabled="#8b95a3",
    color_border="#8591a0",
    color_focus="#8fbaff",
    color_accent="#6ea8fe",
    color_accent_hover="#8fbaff",
    color_accent_pressed="#a9ccff",
    color_on_accent="#0b1220",
    color_selection="#6ea8fe",
    color_on_selection="#0b1220",
    color_danger="#ff9b8f",
    color_button="#2d3641",
    color_button_hover="#3a4553",
    color_button_pressed="#475365",
)

PALETTES = {palette.name: palette for palette in (LIGHT, DARK)}
