from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from btd6.etl.fetch import PROJECT_ROOT

DAMAGE_TYPES: dict[int, tuple[str, set[str]]] = {
    0: ("Normal", set()),
    1: ("Shatter", {"Lead"}),
    2: ("Explosion", {"Black"}),
    4: ("Glacier", {"White"}),
    5: ("Cold", {"Lead", "White"}),
    8: ("Fire", {"Purple"}),
    12: ("Frigid", {"White", "Purple"}),
    17: ("Sharp", {"Lead", "frozen"}),
    64: ("Acid", {"Glass"}),
    72: ("Plasma", {"Purple", "Glass"}),
    73: ("Energy", {"Lead", "Purple", "Glass"}),
}
BLOON_PROPERTIES = ("Lead", "Black", "White", "Purple", "Glass", "frozen")


def first_of(container: dict[str, Any], key: str = "_order") -> tuple[str | None, dict[str, Any]]:
    """Return (name, value) of the first entry in an `_order`-style container."""
    names = container.get(key, [])
    if not names:
        return None, {}
    return names[0], container.get(names[0], {})


def path_from_code(code: str) -> str:
    return "-".join(code.lstrip("_"))


def extract_row(code: str, stats: dict[str, Any]) -> dict[str, Any]:
    _, attack = first_of(stats.get("attacks", {}))
    _, projectile = first_of(attack.get("projectiles", {}))
    _, ability = first_of(stats.get("abilities", {}))

    damage_type, cannot_damage = DAMAGE_TYPES.get(
        projectile.get("immuneBloonProperties", 0), ("Unknown", set())
    )

    row = {
        "path": path_from_code(code),
        "range": stats.get("range"),
        "footprint_radius": stats.get("footprintRadius"),
        "attack_rate": attack.get("rate"),
        "projectile_count": projectile.get("count"),
        "projectile_damage": projectile.get("damage"),
        "projectile_pierce": projectile.get("pierce"),
        "projectile_speed": projectile.get("speed"),
        "projectile_radius": projectile.get("radius"),
        "projectile_lifespan": projectile.get("lifespan"),
        "can_hit_camo": not projectile.get("filterInvisible", False),
        "ability_cooldown": ability.get("cooldown"),
        "damage_type": damage_type,
    }
    for bloon_property in BLOON_PROPERTIES:
        row[f"can_pop_{bloon_property.lower()}"] = bloon_property not in cannot_damage
    return row


def build_dataframe(resolved: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows = (extract_row(code, stats) for code, stats in resolved.items())
    return pd.DataFrame(rows).set_index("path")


def export_csv(json_path: Path | None = None, csv_path: Path | None = None) -> pd.DataFrame:
    if json_path is None:
        json_path = PROJECT_ROOT / "data.json"
    if csv_path is None:
        csv_path = PROJECT_ROOT / "data.csv"
    with open(json_path) as handle:
        resolved = json.load(handle)
    dataframe = build_dataframe(resolved)
    dataframe.to_csv(csv_path)
    return dataframe
