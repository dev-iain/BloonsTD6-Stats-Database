from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from btd6.ui.contrast import BORDER_PAIRS, TEXT_PAIRS, contrast_ratio
from btd6.ui.palettes import PALETTES, Palette

hex_colors = st.integers(0, 0xFFFFFF).map(lambda value: f"#{value:06x}")


def test_black_on_white_is_21() -> None:
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)


def test_same_color_is_1() -> None:
    assert contrast_ratio("#336699", "#336699") == pytest.approx(1.0)


@given(hex_colors, hex_colors)
def test_contrast_is_symmetric_and_at_least_1(first: str, second: str) -> None:
    assert contrast_ratio(first, second) == pytest.approx(contrast_ratio(second, first))
    assert contrast_ratio(first, second) >= 1.0


@pytest.mark.parametrize("palette", PALETTES.values(), ids=lambda palette: palette.name)
@pytest.mark.parametrize(("foreground", "background"), TEXT_PAIRS)
def test_text_pairs_meet_aa(palette: Palette, foreground: str, background: str) -> None:
    ratio = contrast_ratio(getattr(palette, foreground), getattr(palette, background))
    assert ratio >= 4.5, f"{foreground} on {background}: {ratio:.2f}"


@pytest.mark.parametrize("palette", PALETTES.values(), ids=lambda palette: palette.name)
@pytest.mark.parametrize(("foreground", "background"), BORDER_PAIRS)
def test_border_pairs_meet_3_to_1(palette: Palette, foreground: str, background: str) -> None:
    ratio = contrast_ratio(getattr(palette, foreground), getattr(palette, background))
    assert ratio >= 3.0, f"{foreground} on {background}: {ratio:.2f}"


def test_palettes_define_the_same_tokens() -> None:
    light, dark = PALETTES["light"], PALETTES["dark"]
    assert vars(light).keys() == vars(dark).keys()
