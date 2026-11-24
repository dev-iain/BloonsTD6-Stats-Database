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


UNLIMITED = 9999999


def make_attack(name: str, rate: float | None, projectiles: dict[str, dict[str, Any]]) -> tuple:
    """(name, attack dict) with `projectiles` in the given order; None rate is omitted."""
    attack: dict[str, Any] = {} if rate is None else {"rate": rate}
    if projectiles:
        attack["projectiles"] = {"_order": list(projectiles), **projectiles}
    return name, attack


def make_stats(*attacks: tuple, **extra: Any) -> dict[str, Any]:
    """Wiki-shaped stats with every `(name, attack)` pair in `_order` (StatsFactory shell)."""
    container = {"_order": [name for name, _ in attacks], **dict(attacks)}
    return StatsFactory(attacks=container, **extra)


def ninja_003() -> dict[str, Any]:
    return make_stats(
        make_attack(
            "Attack",
            0.62,
            {
                "Flash Bomb": {
                    "pierce": 1,
                    "speed": 300,
                    "radius": 5,
                    "lifespan": 0.57,
                    "immuneBloonProperties": 0,
                },
                "Explosion": {"damage": 3, "pierce": 30, "immuneBloonProperties": 0},
                "Projectile": {
                    "count": 1,
                    "damage": 1,
                    "pierce": 4,
                    "immuneBloonProperties": 17,
                },
            },
        ),
        make_attack(
            "Caltrops",
            3.9,
            {
                "Projectile": {
                    "damage": 1,
                    "pierce": 6,
                    "lifespan": 35,
                    "immuneBloonProperties": 17,
                }
            },
        ),
    )


def wizard_005() -> dict[str, Any]:
    return make_stats(
        make_attack("Attack", 0.275, {"Projectile": {"damage": 1, "pierce": 8}}),
        make_attack("Shimmer", 1, {"Projectile": {"pierce": 500}}),
        make_attack("Reanimate", 1.5, {"Projectile": {"damage": 2, "pierce": 1}}),
        make_attack(
            "MOAB",
            3,
            {"MOAB": {"damage": 40, "pierce": 20}, "BFB": {"damage": 100, "pierce": 50}},
        ),
    )


def druid_vine_attacks() -> tuple:
    return (
        make_attack("Attack", 1.1, {"Projectile": {"damage": 1, "pierce": 1, "count": 8}}),
        make_attack(
            "Vine",
            2.6,
            {
                "Collidable": {"damage": UNLIMITED, "pierce": UNLIMITED},
                "Projectile": {"damage": 1, "pierce": 20},
            },
        ),
    )


def druid_030() -> dict[str, Any]:
    return make_stats(*druid_vine_attacks())


def druid_400() -> dict[str, Any]:
    return make_stats(
        make_attack("Attack", 1.1, {"Projectile": {"damage": 1, "pierce": 2, "count": 5}}),
        make_attack(
            "Ball Lightning",
            6,
            {
                "Spawning projectile": {"damage": 0, "pierce": UNLIMITED},
                "Lightning": {"damage": 3, "pierce": 5},
            },
        ),
        make_attack("Lightning", 2.3, {"Lightning": {"damage": 3, "pierce": 5}}),
        make_attack("Tornado", 2.5, {"Projectile": {"damage": 0, "pierce": 60}}),
    )


def alchemist_220() -> dict[str, Any]:
    return make_stats(make_attack("Acidic Mixture Dip", 10, {}))


def wizard_400() -> dict[str, Any]:
    projectile = {"damage": 6, "pierce": 7, "damageModifierForMoabs": 10}
    return make_stats(make_attack("Attack", 0.275, {"Projectile": projectile}))


ABILITIES_PASSIVE_FIRST = {
    "_order": ["Passive Ability", "Vine Crush"],
    "Passive Ability": {"cooldown": 0},
    "Vine Crush": {"cooldown": 30},
}
ABILITIES_ACTIVE = {"_order": ["Ability"], "Ability": {"cooldown": 60}}


def druid_040() -> dict[str, Any]:
    return make_stats(*druid_vine_attacks(), abilities=ABILITIES_PASSIVE_FIRST)


def alchemist_040() -> dict[str, Any]:
    attack = make_attack("Attack", 2, {"Splash": {"damage": 1, "pierce": 15}})
    return make_stats(attack, abilities=ABILITIES_ACTIVE)


def projectile_of(stats: dict[str, Any], attack: str, projectile: str) -> dict[str, Any]:
    """The mutable projectile dict inside wiki-shaped `stats` (for building variants)."""
    return stats["attacks"][attack]["projectiles"][projectile]


def stored_upgrade_id(connection: Any, tower_name: str, path: str) -> int:
    row = connection.execute(
        "SELECT upgrades.id FROM upgrades JOIN towers ON towers.id = upgrades.tower_id"
        " WHERE towers.name = ? AND upgrades.path = ?",
        (tower_name, path),
    ).fetchone()
    return row[0]
