---
paths:
  - "btd6/etl/**"
---

# ETL rules

- Wiki module JSON: ordered containers use an `_order` list (see `first_of`); crosspath children are keys matching `^_\d{3}$`, inherited from the parent via `deep_merge`.
- `immuneBloonProperties` is a bitmask mapped through `DAMAGE_TYPES`; unknown masks yield `"Unknown"` and must not crash.
- Camo: `can_hit_camo = not filterInvisible`.
- Upgrade codes become paths with `path_from_code` (`_023` -> `0-2-3`).
- Only `fetch_tower_module` / `wiki_api` touch the network. Tests must never call them unmocked.
- `data.json` is generated and gitignored; commit small slices under `tests/fixtures/` instead.
