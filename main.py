import copy
import re
import json
import requests

API_URL = "https://www.bloonswiki.com/api.php"

def wiki_api(**params):
    params["format"] = "json"
    response = requests.get(API_URL, params=params)
    response.raise_for_status()
    return response.json()

outer_content = wiki_api(
    action="query",
    titles="Module:BTD6 stats/Super Monkey/new",
    prop= "revisions",
    rvprop="content",
    rvslots="main",
    formatversion = 2
)


#data manipulation 

CODE_RE = re.compile(r"^_\d{3}$")

def deep_merge(base, override):
    """Recursively overlay override onto a copy of base, merging nested dicts instead of replacing them."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if CODE_RE.match(key):
            continue  # nested crosspath children are handled separately, not merged as fields
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def resolve_all_codes(tower_data):
    """Return {code: fully-resolved stats dict} for every upgrade code, including crosspaths."""
    resolved = {}

    def walk(node, code, parent):
        own_fields = {k: v for k, v in node.items() if not CODE_RE.match(k)}
        merged = deep_merge(parent, own_fields) if parent is not None else own_fields
        resolved[code] = merged
        for key, child in node.items():
            if CODE_RE.match(key):
                walk(child, key, merged)

    for code, node in tower_data.items():
        if CODE_RE.match(code):
            walk(node, code, None)

    return resolved

if __name__ == "__main__":
    inner_content = outer_content["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
    tower_data = json.loads(inner_content)

    resolved = resolve_all_codes(tower_data)
    with open("data.json", "w") as file:
        json.dump(resolved, file, indent=4)