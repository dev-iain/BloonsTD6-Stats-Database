---
paths:
  - "btd6/db/**"
---

# SQLite rules

- Parameterized queries only; never format values into SQL strings.
- `path` ("0-2-3") is the upgrade primary key; `tower_id` is a foreign key to `towers`.
- Normalize: `towers`, `upgrades`, `damage_types` (id = immuneBloonProperties bitmask, name), plus per-bloon-property pop flags. No repeated tower names in `upgrades`.
- Enable `PRAGMA foreign_keys = ON` on every connection; create indexes for columns used in filters/sorts.
- Loading must be idempotent (rebuild or upsert); schema changes go through a numbered migration, then update factories and run the suite.
- Reuse `btd6.etl.extract.extract_row` to produce rows. Do not re-implement extraction.
