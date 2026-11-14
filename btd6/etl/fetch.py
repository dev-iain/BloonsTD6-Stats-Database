from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import requests

API_URL = "https://www.bloonswiki.com/api.php"
CODE_PATTERN = re.compile(r"^_\d{3}$")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
    envelope = wiki_api(
        action="query",
        titles=f"Module:BTD6 stats/{tower_name}/new",
        prop="revisions",
        rvprop="content",
        rvslots="main",
        formatversion=2,
    )
    page = envelope["query"]["pages"][0]
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


def write_resolved_json(tower_name: str, json_path: Path | None = None) -> Path:
    if json_path is None:
        json_path = PROJECT_ROOT / "data.json"
    resolved = resolve_all_codes(fetch_tower_module(tower_name))
    with open(json_path, "w") as handle:
        json.dump(resolved, handle, indent=4)
    return json_path
