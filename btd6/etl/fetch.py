from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from btd6.etl.towers import KNOWN_TOWERS

API_URL = "https://www.bloonswiki.com/api.php"
CODE_PATTERN = re.compile(r"^_\d{3}$")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
STAT_FIELDS = ("range", "footprintRadius")
ATTACK_FIELDS = ("rate",)
PROJECTILE_FIELDS = (
    "count",
    "damage",
    "pierce",
    "speed",
    "radius",
    "lifespan",
    "immuneBloonProperties",
    "filterInvisible",
    "damageModifierForMoabs",
    "filterOutNonMoabs",
)
ABILITY_FIELDS = ("cooldown",)
MAX_ROUND = 100
DEFAULT_ROUNDSET = "DefaultRoundSet"
DEFAULT_INCOME_SET = "DefaultIncomeSet"
BLOON_FIELDS = (
    "id,name,health,health_fort,layers,rbe,rbe_fort,is_moab,speed,immunity,parent_of,child_of"
)
CARGO_PAGE_LIMIT = 500


def wiki_api(**params: str | int) -> dict[str, Any]:
    params["format"] = "json"
    response = requests.get(API_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_tower_module(tower_name: str) -> dict[str, Any]:
    """Fetch a tower's stats module from the wiki and return the parsed Lua-as-JSON content.

    The MediaWiki query returns a page whose first revision's `main` slot holds the module
    source as a JSON string, so the payload has to be decoded twice: once for the API
    envelope and once for the module content itself.
    """
    page = fetch_wiki_page(f"Module:BTD6 stats/{tower_name}/new")
    return decode_page_content(page)


def fetch_rounds_json(label: str, name: str) -> dict[str, Any]:
    page = fetch_wiki_page(f"JSON:Bloons TD 6/Rounds/{name}")
    if page.get("missing"):
        raise ValueError(f'{label} "{name}" not found on the wiki')
    return decode_page_content(page)


def fetch_roundset(name: str = DEFAULT_ROUNDSET) -> dict[str, Any]:
    return fetch_rounds_json("Roundset", name)


def fetch_income_set(name: str = DEFAULT_INCOME_SET) -> dict[str, Any]:
    return fetch_rounds_json("Income set", name)


def cargo_titles(response: dict[str, Any]) -> list[dict[str, Any]]:
    if "error" in response:
        raise ValueError(f"Wiki cargo query failed: {response['error']}")
    return [entry["title"] for entry in response.get("cargoquery", [])]


def cargo_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    rows = cargo_titles(response)
    if not rows:
        raise ValueError("Wiki cargo query returned no rows")
    return rows


def normalize_cargo_keys(title: dict[str, Any]) -> dict[str, Any]:
    return {key.replace(" ", "_"): value for key, value in title.items()}


def fetch_bloons() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = wiki_api(
            action="cargoquery",
            tables="btd6_bloons",
            fields=BLOON_FIELDS,
            limit=CARGO_PAGE_LIMIT,
            offset=offset,
        )
        page = [normalize_cargo_keys(title) for title in cargo_titles(response)]
        rows.extend(page)
        if len(page) < CARGO_PAGE_LIMIT:
            break
        offset += CARGO_PAGE_LIMIT
    if not rows:
        raise ValueError("Wiki cargo query returned no rows")
    return rows


def is_crosspath_upgrade(row: dict[str, Any]) -> bool:
    """Paragons come back as path -1, tier 6, and cut upgrades carry unused=1.

    Neither belongs to an X-Y-Z path.
    """
    if str(row.get("unused") or "0") != "0":
        return False
    return 1 <= int(row["path"]) <= 3 and 1 <= int(row["tier"]) <= 5


def cost_upgrade_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "path": int(row["path"]),
            "tier": int(row["tier"]),
            "cost": int(row["cost"]),
            "name": row["name"],
        }
        for row in rows
        if is_crosspath_upgrade(row)
    ]


def fetch_costs(tower_name: str) -> dict[str, Any]:
    if tower_name not in KNOWN_TOWERS or "'" in tower_name:
        raise ValueError(f'Unknown or invalid tower name "{tower_name}"')
    tower_response = wiki_api(
        action="cargoquery",
        tables="btd6_towers",
        fields="name,cost,category",
        where=f"name='{tower_name}'",
    )
    upgrade_response = wiki_api(
        action="cargoquery",
        tables="btd6_upgrades",
        fields="tower,path,tier,cost,name,unused",
        where=f"tower='{tower_name}'",
        limit=CARGO_PAGE_LIMIT,
    )
    tower_rows = cargo_titles(tower_response)
    if not tower_rows:
        raise ValueError(f'Wiki cargo query returned no rows for tower "{tower_name}"')
    tower_row = tower_rows[0]
    return {
        "base_cost": int(tower_row["cost"]),
        "category": tower_row["category"],
        "upgrades": cost_upgrade_rows(cargo_rows(upgrade_response)),
    }


def fetch_wiki_page(title: str) -> dict[str, Any]:
    envelope = wiki_api(
        action="query",
        titles=title,
        prop="revisions",
        rvprop="content",
        rvslots="main",
        formatversion=2,
    )
    return envelope["query"]["pages"][0]


def decode_page_content(page: dict[str, Any]) -> dict[str, Any]:
    return json.loads(page["revisions"][0]["slots"]["main"]["content"])


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Overlay override onto a copy of base, merging nested dicts instead of replacing them."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if CODE_PATTERN.match(key):
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def resolve_node(
    node: dict[str, Any],
    code: str,
    parent: dict[str, Any] | None,
    resolved: dict[str, dict[str, Any]],
) -> None:
    own_fields = {key: value for key, value in node.items() if not CODE_PATTERN.match(key)}
    merged = deep_merge(parent, own_fields) if parent is not None else own_fields
    resolved[code] = merged
    for key, child in node.items():
        if CODE_PATTERN.match(key):
            resolve_node(child, key, merged, resolved)


def resolve_all_codes(tower_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return {code: fully-resolved stats dict} for every upgrade code, including crosspaths."""
    resolved: dict[str, dict[str, Any]] = {}
    for code, node in tower_data.items():
        if CODE_PATTERN.match(code):
            resolve_node(node, code, None, resolved)
    return resolved


def pick_fields(source: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {name: copy.deepcopy(source[name]) for name in fields if name in source}


def trim_container(
    container: dict[str, Any], trim_entry: Callable[[dict[str, Any]], dict[str, Any]]
) -> dict[str, Any]:
    trimmed: dict[str, Any] = {}
    if "_order" in container:
        trimmed["_order"] = list(container["_order"])
        for name in container["_order"]:
            if name in container:
                trimmed[name] = trim_entry(container[name])
    return trimmed


def trim_projectile(projectile: dict[str, Any]) -> dict[str, Any]:
    return pick_fields(projectile, PROJECTILE_FIELDS)


def trim_ability(ability: dict[str, Any]) -> dict[str, Any]:
    return pick_fields(ability, ABILITY_FIELDS)


def trim_attack(attack: dict[str, Any]) -> dict[str, Any]:
    trimmed = pick_fields(attack, ATTACK_FIELDS)
    if "projectiles" in attack:
        trimmed["projectiles"] = trim_container(attack["projectiles"], trim_projectile)
    return trimmed


def trim_stats(stats: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of stats reduced to the fields the extractor and database use."""
    trimmed = pick_fields(stats, STAT_FIELDS)
    if "attacks" in stats:
        trimmed["attacks"] = trim_container(stats["attacks"], trim_attack)
    if "abilities" in stats:
        trimmed["abilities"] = trim_container(stats["abilities"], trim_ability)
    return trimmed


def write_resolved_json(tower_name: str, json_path: Path | None = None) -> Path:
    if json_path is None:
        json_path = PROJECT_ROOT / "data.json"
    resolved = {
        code: trim_stats(stats)
        for code, stats in resolve_all_codes(fetch_tower_module(tower_name)).items()
    }
    with open(json_path, "w") as handle:
        json.dump(resolved, handle, indent=4)
    return json_path
