# `connect` and `apply_migrations` in `btd6/db/__init__.py`

Table and column names come from `docs/schema.md` and `btd6/db/migrations/001_initial.sql`. All expected values below were confirmed by running the code. Tests use `:memory:` databases except where a file is the thing being tested (use `tmp_path`). A test that needs an older schema version monkeypatches `btd6.db.MIGRATIONS_DIR` to a `tmp_path` directory holding `001_a.sql` and `002_b.sql`.

## connect

```python
def connect(path: str | Path) -> sqlite3.Connection
```

Opens a SQLite database, runs `PRAGMA foreign_keys = ON` and sets `row_factory = sqlite3.Row`. It does not create tables and does not migrate.

Characteristics: the database target decides whether a file is created, reused or cannot be opened (A). Row access by index or by column name is the point of `sqlite3.Row` (B). Foreign key enforcement is the point of the pragma and is observed through the schema, so the tests call `apply_migrations` first (C). The `PRAGMA foreign_keys` value is a functional outcome and is checked in every oracle instead of being modeled.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`path`|A) Database target|A1: In-memory **(Base)**|`":memory:"`|
|||A2: New file, `Path`, parent directory exists|`tmp_path / "new.db"`|
|||A3: Existing file already migrated, `str`|`str(tmp_path / "done.db")` after `apply_migrations` and `commit`|
|||A4: Parent directory missing|`tmp_path / "nope" / "x.db"`|
|returned connection|B) Row access|B1: By column name **(Base)**|`row["name"]`|
|||B2: By index|`row[1]`|
|returned connection (after `apply_migrations`)|C) Foreign key situation|C1: Insert upgrade whose tower exists **(Base)**|`tower_id = 1` after inserting that tower|
|||C2: Insert upgrade whose tower is missing|`tower_id = 999`|
|||C3: Delete a tower that has upgrades|`DELETE FROM towers WHERE id = 1`|

Base case: A1, B1, C1

Excluded or reduced combinations:

- A4 raises before a connection exists, so B and C cannot be observed; it is tested once.
- B and C need the schema, so every test that varies them calls `apply_migrations` first.
- A2 and A3 only differ from A1 in where the data lives; B and C are not repeated for them.

### Base Choice Coverage

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | `PRAGMA foreign_keys` returns `1`; `connection.row_factory is sqlite3.Row`; after `apply_migrations`, inserting tower `(1, "Super Monkey", "Magic")` and then an upgrade `(tower_id=1, path="1-0-0", damage_type_id=1, can_hit_camo=1)` succeeds and `SELECT COUNT(*) FROM upgrades` returns `1`; `SELECT name FROM damage_types WHERE id = 1` gives `row["name"] == "Normal"` | `test_connect_all_base` |
| T2 | A2 | B1 | C1 | `(tmp_path / "new.db").exists()` is `True` after the call; `PRAGMA user_version` returns `0`; `sqlite_master` has no tables; `PRAGMA foreign_keys` returns `1` | `test_connect_new_file` |
| T3 | A3 | B1 | C1 | on the reopened file `PRAGMA user_version` returns `1`; `SELECT COUNT(*) FROM damage_types` returns `12`; `PRAGMA foreign_keys` returns `1` (the pragma is per connection, so it is set again) | `test_connect_existing_migrated_file` |
| T4 | A4 | B1 | C1 | raises `sqlite3.OperationalError` with message `unable to open database file`; no `nope` directory is created | `test_connect_missing_parent_directory` |
| T5 | A1 | B2 | C1 | after `apply_migrations`, `row = SELECT id, name FROM damage_types WHERE id = 1`: `row[0] == 1`, `row[1] == "Normal"`, `tuple(row) == (1, "Normal")`, `row.keys() == ["id", "name"]` | `test_connect_row_access_by_index` |
| T6 | A1 | B1 | C2 | after `apply_migrations`, inserting an upgrade with `tower_id = 999` raises `sqlite3.IntegrityError` with message `FOREIGN KEY constraint failed`; `SELECT COUNT(*) FROM upgrades` returns `0` | `test_connect_foreign_key_missing_tower` |
| T7 | A1 | B1 | C3 | after the T1 inserts, `DELETE FROM towers WHERE id = 1` succeeds and `SELECT COUNT(*) FROM upgrades` returns `0` (`ON DELETE CASCADE`) | `test_connect_foreign_key_cascade_delete` |

## apply_migrations

```python
def apply_migrations(connection: sqlite3.Connection) -> list[str]
```

Applies the `*.sql` scripts in `MIGRATIONS_DIR` whose numeric prefix is greater than `PRAGMA user_version`, in numeric order, setting `user_version` after each. Returns the names applied.

Characteristics: the starting `user_version` decides which scripts run (D). Running it again on the same connection must change nothing (E). A script that fails must not leave the database claiming a version it did not reach (F). The returned list and the resulting tables are functional outcomes, checked in the oracle.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`connection` (state: `user_version`)|D) Starting schema version|D1: Fresh database, version 0 **(Base)**|`connect(":memory:")`|
|||D2: Persisted file already at the latest version|reopened `tmp_path` file, version 1|
|||D3: Older than the latest (1 of 2 scripts applied)|fake dir with `001_a.sql`, `002_b.sql`; `user_version = 1`|
|||D4: Newer than any script|`PRAGMA user_version = 9`|
|`connection` (state)|E) Earlier calls on this connection|E1: First call **(Base)**|none|
|||E2: Second call right after a successful first|`apply_migrations(connection)` twice|
|`MIGRATIONS_DIR`|F) Script content|F1: All scripts valid **(Base)**|real `001_initial.sql`|
|||F2: A later script fails partway|fake dir: `001_a.sql` valid, `002_bad.sql` = `create table c(z); insert into missing values (1);`|

Base case: D1, E1, F1

Excluded or reduced combinations:

- D2, D3 and D4 each already imply a history of earlier migrations, so E2 is not varied with them. E2 is only tested from D1.
- F2 needs a fresh database to reach the failing script, so it is only tested from D1.
- D4 applies nothing, so F is irrelevant there.

### Base Choice Coverage

| BCC Test | D | E | F | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | D1 | E1 | F1 | returns `["001_initial.sql"]`; `PRAGMA user_version` returns `1`; tables are exactly `damage_types`, `towers`, `upgrades`; `SELECT COUNT(*) FROM damage_types` returns `12`; `SELECT COUNT(*) FROM towers` returns `0` | `test_apply_migrations_fresh_database` |
| T2 | D2 | E1 | F1 | on a second connection to the migrated file, returns `[]`; `user_version` still `1`; `SELECT COUNT(*) FROM damage_types` still `12` (the seed is not inserted twice) | `test_apply_migrations_already_latest` |
| T3 | D3 | E1 | F1 | returns `["002_b.sql"]`; `user_version` returns `2`; table `b` exists and `001_a.sql` is not run again | `test_apply_migrations_older_version` |
| T4 | D4 | E1 | F1 | returns `[]`; `user_version` stays `9` | `test_apply_migrations_newer_version` |
| T5 | D1 | E2 | F1 | first call returns `["001_initial.sql"]`, second returns `[]`; `user_version` is `1` after both; `SELECT COUNT(*) FROM damage_types` returns `12` | `test_apply_migrations_twice` |
| T6 | D1 | E1 | F2 | raises `sqlite3.OperationalError` with message `no such table: missing`; `user_version` is `1`, so the next call retries only `002_bad.sql`; table `a` exists | `test_apply_migrations_failing_script` |

Known defect to decide on (T6): `executescript` is not atomic, so the observed result also has table `c` left behind from the failed script, and a retry would then fail with `table c already exists`. The oracle above asserts only the parts that hold today. If the migration runner is changed to roll back a failed script (for example, by running each script in a transaction), add `"c" not in tables` to T6.

Hypothesis property: for any number of consecutive calls `n >= 1`, the first returns the full list and every later call returns `[]`, and `user_version` equals the highest script number.
