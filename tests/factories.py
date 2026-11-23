from __future__ import annotations

from typing import Any

import factory


def path_for_index(index: int) -> str:
    """Unique X-Y-Z style path; digits stay 0-4 except the leading one."""
    return f"{index // 25}-{index // 5 % 5}-{index % 5}"


def build_attacks(
    mask: int, invisible: bool, pierce: int, damage: int, rate: float
) -> dict[str, Any]:
    projectile = {
        "damage": damage,
        "pierce": pierce,
        "immuneBloonProperties": mask,
        "filterInvisible": invisible,
    }
    return {
        "_order": ["attack"],
        "attack": {
            "rate": rate,
            "projectiles": {"_order": ["projectile"], "projectile": projectile},
        },
    }


class UpgradeRowFactory(factory.Factory):
    """Flat row with exactly the keys returned by `extract_row`."""

    class Meta:
        model = dict

    path = factory.Sequence(path_for_index)
    range = 50
    footprint_radius = 5
    attack_rate = 0.5
    projectile_count = 1
    projectile_damage = 1
    projectile_pierce = 2
    projectile_speed = 100
    projectile_radius = 3
    projectile_lifespan = 1.0
    can_hit_camo = True
    ability_cooldown = None
    damage_type = "Normal"
    can_pop_lead = True
    can_pop_black = True
    can_pop_white = True
    can_pop_purple = True
    can_pop_glass = True
    can_pop_frozen = True


class StatsFactory(factory.Factory):
    """Wiki-shaped nested stats dict; params fill the first projectile."""

    class Meta:
        model = dict

    class Params:
        mask = 0
        invisible = False
        pierce = 2
        damage = 1
        rate = 0.5

    range = 50
    attacks = factory.LazyAttribute(
        lambda stats: build_attacks(
            stats.mask, stats.invisible, stats.pierce, stats.damage, stats.rate
        )
    )


class ResultRowFactory(factory.Factory):
    """Mapping shaped like a `search_upgrades` result row (flags stored as 0/1)."""

    class Meta:
        model = dict

    tower_name = "Super Monkey"
    path = factory.Sequence(path_for_index)
    attack_rate = 0.045
    projectile_count = 1
    projectile_damage = 2.0
    projectile_pierce = 3.0
    projectile_speed = 200.0
    can_pop_lead = 1
    can_pop_black = 1
    can_pop_white = 1
    can_pop_purple = 1
    can_pop_glass = 1
    can_pop_frozen = 1
