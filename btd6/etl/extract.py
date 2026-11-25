from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from btd6.etl.fetch import MAX_ROUND, PROJECT_ROOT
from btd6.etl.pop_cash import bloon_pop_cash

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
UNLIMITED = 9999999
BLOON_PROPERTIES = ("Lead", "Black", "White", "Purple", "Glass", "frozen")
BLOON_FLAG_COLUMNS = tuple(f"has_{name.lower()}" for name in BLOON_PROPERTIES)


def first_of(container: dict[str, Any], key: str = "_order") -> tuple[str | None, dict[str, Any]]:
    """Return (name, value) of the first entry in an `_order`-style container."""
    names = container.get(key, [])
    if not names:
        return None, {}
    return names[0], container.get(names[0], {})


def path_from_code(code: str) -> str:
    return "-".join(code.lstrip("_"))


def limited_value(value: float | None) -> float | None:
    return None if value == UNLIMITED else value


def damage_type_name(mask: int) -> str:
    return DAMAGE_TYPES.get(mask, ("Unknown", set()))[0]


def is_positive_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and value > 0


def extract_effect_rows(effects: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the damaging effects of one projectile, keeping their `_order` position."""
    rows: list[dict[str, Any]] = []
    for index, name in enumerate(effects.get("_order", [])):
        effect = effects.get(name, {})
        if not is_positive_number(effect.get("damage")):
            continue
        if not is_positive_number(effect.get("interval")):
            continue
        rows.append(
            {
                "effect_index": index,
                "name": name,
                "damage": effect["damage"],
                "tick_interval": effect["interval"],
                "lifespan": effect.get("lifespan", 0),
                "trigger_immediate": bool(effect.get("triggerImmediate", False)),
                "moab_bonus_damage": effect.get("damageModifierForMoabs"),
                "moab_only": bool(effect.get("filterOutNonMoabs", False)),
                "damage_type": damage_type_name(effect.get("immuneBloonProperties", 0)),
            }
        )
    return rows


def extract_projectile_row(index: int, name: str, projectile: dict[str, Any]) -> dict[str, Any]:
    damage_type = damage_type_name(projectile.get("immuneBloonProperties", 0))
    damage = projectile.get("damage")
    pierce = projectile.get("pierce")
    return {
        "projectile_index": index,
        "name": name,
        "damage": limited_value(damage),
        "pierce": limited_value(pierce),
        "unlimited_damage": damage == UNLIMITED,
        "unlimited_pierce": pierce == UNLIMITED,
        "moab_bonus_damage": projectile.get("damageModifierForMoabs"),
        "moab_only": bool(projectile.get("filterOutNonMoabs", False)),
        "count": projectile.get("count"),
        "speed": projectile.get("speed"),
        "radius": projectile.get("radius"),
        "lifespan": projectile.get("lifespan"),
        "damage_type": damage_type,
        "can_hit_camo": not projectile.get("filterInvisible", False),
        "effects": extract_effect_rows(projectile.get("effects", {})),
    }


def extract_attack_rows(stats: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten every attack and its projectiles, in wiki `_order`, into plain dicts."""
    container = stats.get("attacks", {})
    rows: list[dict[str, Any]] = []
    for attack_index, attack_name in enumerate(container.get("_order", [])):
        attack = container.get(attack_name, {})
        projectiles = attack.get("projectiles", {})
        rows.append(
            {
                "attack_index": attack_index,
                "name": attack_name,
                "rate": attack.get("rate"),
                "projectiles": [
                    extract_projectile_row(index, name, projectiles.get(name, {}))
                    for index, name in enumerate(projectiles.get("_order", []))
                ],
            }
        )
    return rows


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
        "projectile_damage": limited_value(projectile.get("damage")),
        "projectile_pierce": limited_value(projectile.get("pierce")),
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
CHILD_NOISE_WORDS = frozenset({"Bloon", *MODIFIER_SUFFIXES})
LINK_PATTERN = re.compile(r"\[\[([^\]|]*)(?:\|([^\]]*))?\]\]")
CHILD_PATTERN = re.compile(r"\u00d7\s*(\d+)")


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


def immune_damage_types(immunity: str | None) -> set[str]:
    labels = link_labels(immunity or "")
    return {part.strip().lower() for part in labels.split(",") if part.strip()}


def parse_bloon_properties(immunity: str | None) -> dict[str, int]:
    """Map a Cargo `immunity` text (damage types) to the six bloon property flags.

    A property is set when every damage type blocked by it is listed. `frozen` is a state,
    not something a bloon carries, so it is never set (see `docs/data-notes.md`).
    """
    listed = immune_damage_types(immunity)
    flags: dict[str, int] = {}
    for bloon_property in BLOON_PROPERTIES:
        blocked = {
            name.lower()
            for name, cannot_damage in DAMAGE_TYPES.values()
            if bloon_property in cannot_damage
        }
        carries = bloon_property != "frozen" and bool(blocked) and blocked <= listed
        flags[f"has_{bloon_property.lower()}"] = int(carries)
    return flags


def extract_bloon_row(raw: dict[str, str]) -> dict[str, Any]:
    name = str(raw.get("id") or "").strip()
    if not name:
        raise ValueError("Bloon row has an empty name (Cargo id)")
    row: dict[str, Any] = {"name": name}
    for field in BLOON_INTEGER_FIELDS:
        row[field] = parse_number(raw, field, int)
    row["is_moab"] = parse_is_moab(raw)
    row["speed"] = parse_number(raw, "speed", float)
    row.update(parse_bloon_properties(raw.get("immunity")))
    return row


def link_labels(text: str) -> str:
    return LINK_PATTERN.sub(lambda match: match.group(2) or match.group(1), text)


def parse_child_name(text: str) -> str:
    words = [word for word in text.split() if word not in CHILD_NOISE_WORDS]
    return " ".join(words).title()


def parse_bloon_children(parent_of: str) -> list[tuple[str, int]]:
    """Parse a Cargo `parent of` text into ordered (child name, count) pairs, one per entry."""
    children: list[tuple[str, int]] = []
    for segment in link_labels(parent_of).split(","):
        match = CHILD_PATTERN.search(segment)
        if match:
            children.append((parse_child_name(segment[: match.start()]), int(match.group(1))))
    return children


def extract_bloon_rows(raw: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows = [extract_bloon_row(entry) for entry in raw]
    children = {
        row["name"]: parse_bloon_children(str(entry.get("parent_of") or ""))
        for row, entry in zip(rows, raw, strict=True)
    }
    moab_names = frozenset(row["name"] for row in rows if row["is_moab"])
    for row in rows:
        row["pop_cash"] = bloon_pop_cash(row["name"], children, moab_names, False)
        row["pop_cash_super"] = bloon_pop_cash(row["name"], children, moab_names, True)
    return rows


def extract_income_thresholds(income_set: dict[str, Any]) -> list[dict[str, Any]]:
    thresholds = income_set.get("thresholds")
    items = thresholds.get("items") if isinstance(thresholds, dict) else None
    if not isinstance(items, list):
        raise ValueError('income set has no "thresholds.items" list')
    return [
        {"max_round": int(item["threshold"]), "multiplier": float(item["multiplier"])}
        for item in items
    ]


def extract_final_multiplier(income_set: dict[str, Any]) -> float:
    if "finalMultiplier" not in income_set:
        raise ValueError('income set has no "finalMultiplier"')
    return income_set["finalMultiplier"]


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
