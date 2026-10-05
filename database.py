import json

import pandas as pd

with open("data.json") as f:
    resolved = json.load(f)


DAMAGE_TYPES = {
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


def extract_row(code, stats):
    attacks = stats.get("attacks", {})
    attack_name = attacks.get("_order", [None])[0]
    attack = attacks.get(attack_name, {}) if attack_name else {}

    projectiles = attack.get("projectiles", {})
    projectile_name = projectiles.get("_order", [None])[0]
    projectile = projectiles.get(projectile_name, {}) if projectile_name else {}

    abilities = stats.get("abilities", {})
    ability_name = abilities.get("_order", [None])[0]
    ability = abilities.get(ability_name, {}) if ability_name else {}

    damage_type_name, cant_damage = DAMAGE_TYPES.get(
        projectile.get("immuneBloonProperties", 0), ("Unknown", set())
    )

    row = {
        "code": code,
        "range": stats.get("range"),
        "footprint_radius": stats.get("footprintRadius"),
        "cooldown": attack.get("rate"),
        "projectile_damage": projectile.get("damage"),
        "projectile_pierce": projectile.get("pierce"),
        "projectile_speed": projectile.get("speed"),
        "projectile_radius": projectile.get("radius"),
        "ability_cooldown": ability.get("cooldown"),
        "damage_type": damage_type_name,
    }
    for prop in BLOON_PROPERTIES:
        row[f"can_pop_{prop.lower()}"] = prop not in cant_damage

    return row


rows = [extract_row(code, stats) for code, stats in resolved.items()]

df = pd.DataFrame(rows)
df = df.rename(columns={"code": "path"})
df = df.set_index("path")

df.index = df.index.map(lambda code: "-".join(code.lstrip("_"))) # rename from _000 to standard 0-0-0
print(df.to_string())
print()
print("Codes that can pop Lead:")
print(df[df["can_pop_lead"]].index.tolist())
