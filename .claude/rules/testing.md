---
paths:
  - "tests/**"
---

# Testing rules

- Test first: a failing test exists before any `btd6/` source changes (enforced by the `require_test_first` hook).
- Partition inputs with ISP/boundary tables (range, pierce, damage, `damage_type`, camo, `can_pop_*`) and turn each partition into a `pytest.mark.parametrize` case.
- Build tower/upgrade rows with factory_boy factories in `tests/factories.py`; do not hand-write 19-column dicts.
- Use hypothesis for invariants (e.g. filtering never returns rows violating the filter; reload is idempotent).
- Use SQLite `:memory:` databases. Never mock SQLite and never hit the wiki network; use fixtures under `tests/fixtures/`.
- `data.csv` is the golden regression fixture for `extract_row` (64 Super Monkey upgrades).
- Tests follow the same style rules as source except `ANN` type hints are optional.
