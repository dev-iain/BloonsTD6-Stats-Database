from __future__ import annotations

from btd6.etl.towers import MAGIC_TOWERS


def test_magic_towers_exact_order() -> None:
    assert MAGIC_TOWERS == ("Super Monkey", "Wizard Monkey", "Ninja Monkey", "Alchemist", "Druid")


def test_magic_towers_is_immutable_tuple_of_unique_names() -> None:
    assert isinstance(MAGIC_TOWERS, tuple)
    assert len(set(MAGIC_TOWERS)) == len(MAGIC_TOWERS)
