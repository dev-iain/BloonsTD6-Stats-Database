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


class UpgradeCostRowFactory(factory.Factory):
    """One `fetch_costs` upgrade row; path/tier cycle through all 15 slots."""

    class Meta:
        model = dict

    path = factory.Sequence(lambda index: index // 5 % 3 + 1)
    tier = factory.Sequence(lambda index: index % 5 + 1)
    cost = factory.LazyAttribute(lambda upgrade: 100 * upgrade.tier)
    name = factory.LazyAttribute(lambda upgrade: f"Upgrade {upgrade.path}-{upgrade.tier}")


class CostsFactory(factory.Factory):
    """`fetch_costs` output with all 15 upgrades; every price is 100 x tier."""

    class Meta:
        model = dict

    base_cost = 1000
    category = "Magic"
    upgrades = factory.LazyFunction(
        lambda: [
            UpgradeCostRowFactory.build(path=path, tier=tier)
            for path in (1, 2, 3)
            for tier in range(1, 6)
        ]
    )


SUPER_MONKEY_COSTS = {
    1: [2000, 2500, 20000, 100000, 500000],
    2: [1500, 1900, 7500, 25000, 70000],
    3: [3000, 1200, 5600, 55555, 165650],
}


def super_monkey_costs() -> dict[str, Any]:
    upgrades = [
        UpgradeCostRowFactory.build(path=path, tier=tier, cost=prices[tier - 1])
        for path, prices in SUPER_MONKEY_COSTS.items()
        for tier in range(1, 6)
    ]
    return CostsFactory.build(base_cost=2500, upgrades=upgrades)


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


DEFAULT_THRESHOLDS = [(50, 1), (60, 0.5), (85, 0.2), (100, 0.1), (120, 0.05), (140, 0.04)]


class ThresholdItemFactory(factory.Factory):
    """One `{"threshold", "multiplier"}` entry of the wiki income set."""

    class Meta:
        model = dict

    threshold = factory.Sequence(lambda index: 50 * (index + 1))
    multiplier = 1


class IncomeSetFactory(factory.Factory):
    """Wiki `DefaultIncomeSet` shape; pass `thresholds=[...]` items to override."""

    class Meta:
        model = dict

    finalMultiplier = 0.02  # noqa: N815
    thresholds = factory.LazyAttribute(
        lambda _: {
            "items": [
                ThresholdItemFactory(threshold=limit, multiplier=value)
                for limit, value in DEFAULT_THRESHOLDS
            ]
        }
    )

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        items = kwargs.pop("items", None)
        if items is not None:
            kwargs["thresholds"] = {"items": items}
        return model_class(*args, **kwargs)


class RawBloonFactory(factory.Factory):
    """Normalised Cargo bloon row (underscore keys) as returned by `fetch_bloons`."""

    class Meta:
        model = dict

    id = "Red"
    name = factory.LazyAttribute(lambda row: f"{row.id} Bloon")
    health = "1"
    health_fort = ""
    layers = "1"
    rbe = "1"
    rbe_fort = ""
    is_moab = ""
    speed = "25"
    immunity = ""
    parent_of = ""
    child_of = ""
