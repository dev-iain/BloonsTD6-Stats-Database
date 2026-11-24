# Bloon properties: `parse_bloon_properties` and `extract_bloon_row`

## Rules for these tests

- Both live in `btd6/etl/extract.py`. Source and verified values: `docs/data-notes.md`, "Bloon properties". Fixture: `tests/fixtures/bloons_immunity_cargo_response.json` (17 bloons, spaced Cargo keys; normalize with `normalize_cargo_keys` first).
- The six flags are `has_lead, has_black, has_white, has_purple, has_glass, has_frozen`, each `0` or `1` (int, matching the `INTEGER NOT NULL` columns).
- Cargo `immunity` lists damage types, not properties. A flag is `1` when **every** damage type in `DAMAGE_TYPES` whose `cannot_damage` contains that property appears in the text. `has_frozen` is always `0` (the `Sharp` type is only listed because of `Lead`). Status effects (`Slow`, `blowback`, `knockback`) are ignored.
- Wiki links `[[damage type|Sharp, Shatter]]` are reduced to their label first (`link_labels`); damage-type names are matched as whole words, case-insensitively, after splitting on commas.
- An empty, missing or `None` `immunity` gives six `0` flags.
- `extract_bloon_row` output gains the six flags after `speed`, in the order above; `is_moab` does not change them.

---

## parse_bloon_properties

```python
def parse_bloon_properties(immunity: str | None) -> dict[str, int]
```

Maps a Cargo `immunity` text to the six property flags.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`immunity`|A) Content|A1: Empty|`""`|
|||A2: Status effects only|`"[[Slow]], [[blowback]], [[knockback]]"`|
|||A3: All types of one property **(Base)**|`"[[damage type\|Sharp, Shatter, Cold, Energy]]"` (Lead)|
|||A4: All types of two properties|`"[[damage type\|Explosion, Cold, Glacier, Frigid]]"` (Zebra: Black and White)|
|||A5: Only some types of a property|`"[[damage type\|Sharp]]"`|
|||A6: Glass types|`"Energy, Plasma, Acid"`|
|||A7: `None`|`None`|
|`immunity`|B) Markup|B1: Wiki link **(Base)**|`"[[damage type\|Sharp, Shatter, Cold, Energy]]"`|
|||B2: Plain text|`"Sharp, Shatter, Cold, Energy"`|

Base case: A3, B1

### BCC

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A3 | B1 | `has_lead` is `1`, the other five are `0` | `test_parse_bloon_properties_lead` |
| T2 | A1 | B1 | all six `0` | `test_parse_bloon_properties_empty` |
| T3 | A2 | B1 | all six `0` | `test_parse_bloon_properties_status_effects_only` |
| T4 | A4 | B1 | `has_black` and `has_white` `1`, rest `0` | `test_parse_bloon_properties_zebra` |
| T5 | A5 | B1 | all six `0` (`Sharp` alone proves neither `Lead` nor `frozen`) | `test_parse_bloon_properties_partial_types` |
| T6 | A6 | B1 | `has_glass` `1`, rest `0` | `test_parse_bloon_properties_glass` |
| T7 | A7 | B1 | all six `0` | `test_parse_bloon_properties_none` |
| T8 | A3 | B2 | `has_lead` `1`, rest `0` | `test_parse_bloon_properties_plain_text` |

Extra (not BCC): the Ddt text (`Sharp, Shatter, Cold, Energy, Explosion`) gives `has_lead` and `has_black` and never `has_frozen` (`test_parse_bloon_properties_never_frozen`).

---

## extract_bloon_row (properties)

```python
def extract_bloon_row(raw: dict[str, str]) -> dict[str, Any]
```

Existing behavior is unchanged (`docs`: `tests/isp-tables/bloons.md`); this table covers the added flags.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`raw["immunity"]`|C) Source row|C1: Lead row **(Base)**|Cargo `Lead` row|
|||C2: All-empty `immunity`|Cargo `Red` row|
|||C3: Several properties|Cargo `Zebra` row|
|||C4: Key absent|`Red` row without the `immunity` key|
|`raw["is_moab"]`|D) MOAB class|D1: Not a MOAB **(Base)**|`""`|
|||D2: MOAB-class|`"1"` (Ddt row: Lead and Black)|

Base case: C1, D1

### BCC

| BCC Test | C | D | Oracle | Test Name |
|---|---|---|---|---|
| T1 | C1 | D1 | `has_lead` `1`, other flags `0` | `test_extract_bloon_row_lead_flag` |
| T2 | C2 | D1 | all six flags `0` | `test_extract_bloon_row_no_properties` |
| T3 | C3 | D1 | `has_black` and `has_white` `1` | `test_extract_bloon_row_several_properties` |
| T4 | C4 | D1 | all six flags `0`, no error | `test_extract_bloon_row_missing_immunity` |
| T5 | C1 | D2 | `is_moab` `True`, `has_lead` `1` (flags independent of MOAB class) | `test_extract_bloon_row_moab_flags_independent` |

Fixture checks (not BCC): Black has only `has_black`, Purple only `has_purple`, Ddt has `has_lead` and `has_black`, Bad and Ceramic have none (`test_extract_bloon_row_fixture_flags`).
