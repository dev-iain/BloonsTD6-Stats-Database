from __future__ import annotations

TEXT_PAIRS = (
    ("color_text", "color_background"),
    ("color_text", "color_surface"),
    ("color_text", "color_surface_alt"),
    ("color_text", "color_header"),
    ("color_text_muted", "color_background"),
    ("color_text_muted", "color_surface"),
    ("color_text_muted", "color_surface_alt"),
    ("color_danger", "color_background"),
    ("color_danger", "color_surface"),
    ("color_accent", "color_background"),
    ("color_on_accent", "color_accent"),
    ("color_on_accent", "color_accent_hover"),
    ("color_on_accent", "color_accent_pressed"),
    ("color_on_selection", "color_selection"),
    ("color_text", "color_button"),
    ("color_text", "color_button_hover"),
    ("color_text", "color_button_pressed"),
)
BORDER_PAIRS = (
    ("color_border", "color_background"),
    ("color_border", "color_surface"),
    ("color_focus", "color_background"),
    ("color_focus", "color_surface"),
    ("color_text_disabled", "color_background"),
)


def channel_luminance(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    red, green, blue = (int(color[index : index + 2], 16) for index in (1, 3, 5))
    return (
        0.2126 * channel_luminance(red)
        + 0.7152 * channel_luminance(green)
        + 0.0722 * channel_luminance(blue)
    )


def contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (relative_luminance(foreground), relative_luminance(background)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)
