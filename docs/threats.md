# Round threats

`btd6/threats.py`: `round_threats(connection, round_number) -> RoundThreats` summarises what a round demands from the towers. ISP/BCC tables: `tests/isp-tables/threats.md` and `tests/isp-tables/bloon_properties.md`.

## Pop rule

An upgrade can pop bloon B iff for every property B has, the upgrade's `can_pop_<property>` is true. Properties are `lead, black, white, purple, glass, frozen`; bloon flags are `bloons.has_<property>` (migration 005), upgrade flags are `can_pop_<property>`. Camo is separate: an upgrade can hit a camo group iff `can_hit_camo`.

## Group RBE

For each round group: `count * rbe`, or `count * rbe_fort` when `is_fortified` and `rbe_fort` is not NULL (a fortified group whose bloon has no `rbe_fort` falls back to `rbe`). A group whose result is NULL (`rbe` NULL) is excluded from every total and share and counted in `unknown_groups`.

## Outputs

| Field | Definition |
|---|---|
| `total_rbe` | sum of group RBE (known groups only) |
| `unknown_groups` | number of groups with no computable RBE |
| `property_share[prop]` | RBE of groups whose bloon has `has_<prop>`, divided by `total_rbe`; a group counts toward every property it carries, so the shares can sum to more than 1 |
| `camo_share`, `regrow_share`, `moab_share` | RBE of groups with `is_camo`, `is_regrow`, `is_moab`, divided by `total_rbe` |
| `mean_layers` | `sum(group RBE * bloons.layers) / total_rbe` (a NULL `layers` counts as 0) |

When `total_rbe` is 0 (empty round or every group unknown) every share and `mean_layers` is `0.0`. Errors come from `validate_round`: `TypeError` for a non-int (including `bool`), `ValueError` for a round below 1 or above the highest loaded, `NoRoundDataError` when no rounds are loaded.

## Expected values (wiki data of 2026-11-23, rounds 1-100)

| Round | `total_rbe` | Notable shares | `mean_layers` |
|---|---|---|---|
| 40 | 616 | `moab_share` 1.0 (a single MOAB), all properties 0 | 10.0 |
| 63 | 14413 | `property_share["lead"]` 0.1197 (75 Lead, 122 Ceramic), other properties 0, `camo_share` 0.0 | 8.76 |

Round 63 has no camo in the wiki's `DefaultRoundSet` (groups: Lead x75, Ceramic x40, x40, x42, none with a Camo suffix), so `camo_share` is 0 there, contrary to the epic text. Lead is the only property carried (ceramic has none), so it is the largest property share. A recommender that wants pierce for round 63 must get it from the ceramic RBE share (`mean_layers`), not from a property.

## Reload note

Migration 005 adds the flag columns with `DEFAULT 0`, so a database migrated without reloading reads every bloon as having no properties. Run `python -m btd6 load` after upgrading.
