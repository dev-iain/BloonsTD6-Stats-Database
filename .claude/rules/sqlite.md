---
paths:
  - "btd6/db/**"
---

# SQLite rules

- Parameterized queries only; never format values into SQL strings.
- An upgrade is identified by `(tower_id, path)`: `path` ("0-2-3") repeats across towers, so it is never unique on its own. `tower_id` is a foreign key to `towers`.
- Normalize: `towers`, `upgrades`, `damage_types` (name, plus `Unknown`; `extract_row` yields the name, not the bitmask), plus per-bloon-property pop flags. No repeated tower names in `upgrades`. Final decisions live in `docs/schema.md` (issue #16).
- Enable `PRAGMA foreign_keys = ON` on every connection; create indexes for columns used in filters/sorts.
- Loading must be idempotent (rebuild or upsert); schema changes go through a numbered migration, then update factories and run the suite.
- Reuse `btd6.etl.extract.extract_row` to produce rows. Do not re-implement extraction.
