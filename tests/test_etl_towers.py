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
        "Tack Shooter",
        "Glue Gunner",
        "Desperado",
        "Monkey Sub",
        "Monkey Buccaneer",
        "Monkey Ace",
        "Heli Pilot",
        "Mortar Monkey",
        "Dartling Gunner",
        "Mermonkey",
        "Spike Factory",
        "Engineer Monkey",
        "Beast Handler",
    )


def test_known_towers_is_magic_then_extra_without_duplicates() -> None:
    assert KNOWN_TOWERS == MAGIC_TOWERS + EXTRA_TOWERS
    assert len(set(KNOWN_TOWERS)) == len(KNOWN_TOWERS)


def test_known_towers_count_is_every_tower_with_wiki_stats() -> None:
    assert len(KNOWN_TOWERS) == 23


def test_known_towers_skip_towers_without_wiki_attack_stats() -> None:
    for name in ("Banana Farm", "Monkey Village", "Skywarden", "Monkey Academy"):
        assert name not in KNOWN_TOWERS
