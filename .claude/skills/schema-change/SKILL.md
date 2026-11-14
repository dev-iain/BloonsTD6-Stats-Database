---
name: schema-change
description: Safe procedure for changing the SQLite schema (new column, table, or index). Use whenever btd6/db DDL changes.
---

# Schema change

1. Write/adjust the failing test first (loader round-trip against `data.csv`).
2. Add a numbered migration in `btd6/db/migrations/`; never edit an applied migration.
3. Update the factory in `tests/factories.py` and the loader.
4. Run the `schema-reviewer` agent on the DDL for normalization and index choices.
5. Run `uv run pytest`; the reload-idempotency test must still pass.
6. Tell Nicole (query owner) which columns changed, since the schema is the contract between loader and queries.
