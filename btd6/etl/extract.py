from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from btd6.etl.fetch import MAX_ROUND, PROJECT_ROOT

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


def extract_round_rows(
    roundset: dict[str, Any], max_round: int = MAX_ROUND
) -> list[dict[str, Any]]:
    if max_round < 1:
        raise ValueError(f"max_round must be at least 1, got {max_round}")
    rounds = roundset.get("rounds")
    if not isinstance(rounds, list):
        raise ValueError('roundset has no "rounds" list')
    rows: list[dict[str, Any]] = []
    for index, round_data in enumerate(rounds[:max_round]):
        rows.extend(build_group_rows(index + 1, round_data))
    return rows


def build_group_rows(round_number: int, round_data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "round": round_number,
            "group_index": group_index,
            "bloon": group["bloon"],
            "count": group["count"],
            "start": group["start"],
            "duration": group["duration"],
        }
        for group_index, group in enumerate(round_data.get("bloonGroups", []))
    ]


BLOON_INTEGER_FIELDS = ("health", "health_fort", "layers", "rbe", "rbe_fort")
MODIFIER_SUFFIXES = ("Fortified", "Camo", "Regrow")


def parse_number(
    raw: dict[str, str], field: str, convert: Callable[[str], int | float]
) -> int | float | None:
    text = str(raw.get(field) or "").strip()
    if not text:
        return None
    try:
        return convert(text)
    except ValueError:
        raise ValueError(
            f"Bloon {str(raw.get('id', '')).strip()!r} has non-numeric {field}: {text!r}"
        ) from None


def parse_is_moab(raw: dict[str, str]) -> bool:
    text = str(raw.get("is_moab") or "").strip()
    if text not in ("", "0", "1"):
        raise ValueError(f'Bloon {raw.get("id")!r} has invalid is_moab: "{text}"')
    return text == "1"


def extract_bloon_row(raw: dict[str, str]) -> dict[str, Any]:
    name = str(raw.get("id") or "").strip()
    if not name:
        raise ValueError("Bloon row has an empty name (Cargo id)")
    row: dict[str, Any] = {"name": name}
    for field in BLOON_INTEGER_FIELDS:
        row[field] = parse_number(raw, field, int)
    row["is_moab"] = parse_is_moab(raw)
    row["speed"] = parse_number(raw, "speed", float)
    return row


def extract_bloon_rows(raw: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [extract_bloon_row(entry) for entry in raw]


def split_bloon_name(name: str) -> tuple[str, bool, bool, bool]:
    if not name:
        raise ValueError("Cannot split an empty bloon name")
    found: set[str] = set()
    base = name
    stripped = True
    while stripped:
        stripped = False
        for suffix in MODIFIER_SUFFIXES:
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                found.add(suffix)
                stripped = True
    if not base:
        raise ValueError(f"Bloon name {name!r} has no base bloon")
    return base, "Camo" in found, "Regrow" in found, "Fortified" in found
