from __future__ import annotations

from btd6.etl.towers import EXTRA_TOWERS, KNOWN_TOWERS, MAGIC_TOWERS


def test_magic_towers_exact_order() -> None:
    assert MAGIC_TOWERS == ("Super Monkey", "Wizard Monkey", "Ninja Monkey", "Alchemist", "Druid")


def test_magic_towers_is_immutable_tuple_of_unique_names() -> None:
    assert isinstance(MAGIC_TOWERS, tuple)
    assert len(set(MAGIC_TOWERS)) == len(MAGIC_TOWERS)


def test_extra_towers_exact_order() -> None:
    assert EXTRA_TOWERS == (
        "Dart Monkey",
        "Boomerang Monkey",
        "Bomb Shooter",
        "Sniper Monkey",
        "Ice Monkey",
    )


def test_known_towers_is_magic_then_extra_without_duplicates() -> None:
    assert KNOWN_TOWERS == MAGIC_TOWERS + EXTRA_TOWERS
    assert len(set(KNOWN_TOWERS)) == len(KNOWN_TOWERS)
