# `deep_merge` and `resolve_all_codes` in `btd6/etl/fetch.py`

The wiki stores each upgrade as a node holding only the fields that change relative to its parent. Child upgrades are nested inside the parent under keys matching `^_\d{3}$`. `resolve_all_codes` walks that tree and uses `deep_merge(parent_resolved, own_fields)` so a child inherits every parent stat and overrides only what it changes.

All expected values below were confirmed by running the code.

## deep_merge

```python
def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]
```

Returns a deep copy of `base` with `override` laid on top. A scalar override replaces; nested dicts merge key by key; a dict replacing a scalar (or the reverse) replaces; override keys matching `_NNN` are skipped; `base` is never modified.

We model each key in `override`, since the override is applied onto the base. What happens to a key depends on the type of `override[key]` (scalar or nested dict) and on what `base` holds for the same key, so these are two characteristics whose combination gives the behavior. A crosspath key is skipped before any type check, so it is its own characteristic. An empty `override` has no key to compare, so it is modeled separately. Whether `base` is left untouched is a functional outcome and is checked in every oracle, not modeled.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`override`|A) Type of `override["attacks"]`|A1: Scalar|`0`|
|||A2: Nested dict **(Base)**|`{"rate": 0.5}`|
|`base`|B) State of `base["attacks"]`|B1: Absent|`{}`|
|||B2: Dict **(Base)**|`{"rate": 1.0, "count": 1}`|
|||B3: Scalar|`0`|
|`override`|C) Key is a crosspath code|C1: Normal field **(Base)**|`{"attacks": {"rate": 0.5}}`|
|||C2: Key matches `_NNN`|`{"_012": {"range": 90}}`|
|||C3: Key looks like a code but does not match|`{"_12": {"range": 90}}`|
|`override`|D) Override is empty|D1: Non-empty **(Base)**|`{"attacks": {"rate": 0.5}}`|
|||D2: Empty|`{}`|

Base case: A2, B2, C1, D1

Excluded or reduced combinations:

- C2 and D2 make A and B irrelevant (a crosspath key is skipped before the type check, and an empty override has no key), so each is tested once with A and B at base.
- C3 is copied like any normal field, so A and B are irrelevant there as well.
- Every A x B combination is otherwise feasible; the BCC set uses the base value of the other one.

### Base Choice Coverage

| BCC Test | A | B | C | D | Oracle | Test Name |
|---|---|---|---|---|---|---|
| T1 | A2 | B2 | C1 | D1 | `deep_merge({"attacks": {"rate": 1.0, "count": 1}}, {"attacks": {"rate": 0.5}})` returns `{"attacks": {"rate": 0.5, "count": 1}}`; `base` still equals `{"attacks": {"rate": 1.0, "count": 1}}` | `test_deep_merge_both_dicts` |
| T2 | A1 | B2 | C1 | D1 | `deep_merge({"attacks": {"rate": 1.0, "count": 1}}, {"attacks": 0})` returns `{"attacks": 0}`; `base` unchanged | `test_deep_merge_scalar_replaces_dict` |
| T3 | A2 | B1 | C1 | D1 | `deep_merge({}, {"attacks": {"rate": 0.5}})` returns `{"attacks": {"rate": 0.5}}` | `test_deep_merge_key_absent_in_base` |
| T4 | A2 | B3 | C1 | D1 | `deep_merge({"attacks": 0}, {"attacks": {"rate": 0.5}})` returns `{"attacks": {"rate": 0.5}}` | `test_deep_merge_dict_replaces_scalar` |
| T5 | A2 | B2 | C2 | D1 | `deep_merge({"range": 50}, {"_012": {"range": 90}})` returns `{"range": 50}`; `"_012" not in result` | `test_deep_merge_crosspath_key_skipped` |
| T6 | A2 | B2 | C3 | D1 | `deep_merge({"range": 50}, {"_12": {"range": 90}})` returns `{"range": 50, "_12": {"range": 90}}` | `test_deep_merge_malformed_code_copied` |
| T7 | A2 | B2 | C1 | D2 | `deep_merge({"range": 50}, {})` returns `{"range": 50}`; `result is not base` | `test_deep_merge_empty_override` |

T5 to T7 do not use the base A and B inputs literally, since a crosspath key, a malformed key or an empty override has nothing to merge; their A and B selections are base labels only.

Hypothesis properties: for any `base`, `deep_merge(base, {})` equals `base` and `base` is never mutated; mutating the result never changes `base`.

## resolve_all_codes

```python
def resolve_all_codes(tower_data: dict[str, Any]) -> dict[str, dict[str, Any]]
```

Returns `{code: fully-resolved stats dict}` for every upgrade code, including nested crosspaths. Only top-level keys matching `_NNN` are processed (the wiki module has 17 top-level keys but 64 upgrade codes once nested). A top-level upgrade starts from its own fields; a child sees its parent's merged stats; siblings never affect each other; empty input returns `{}`.

We model the shape of `tower_data`. Which top-level keys are processed depends on whether they match the code pattern, so we model the kind of top-level key. The tree depth decides how many merge steps stack, so we model the nesting depth. What a child changes decides whether inheritance, override or partial dict merge happens, so we model the child's own fields. Siblings are modeled because a shared parent must not be changed by one child while resolving another. Empty input returns `{}` and is modeled separately. The resolved value of each code is the functional outcome and is checked in the oracle.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`tower_data`|E) Top-level keys|E1: Only `_NNN` keys **(Base)**|`{"_100": {...}}`|
|||E2: Also a non-code key|`{"range": 50, "_100": {"range": 60}}`|
|||E3: Also a malformed code key|`{"_01": {"range": 3}, "_100": {"range": 60}}`|
|`tower_data`|F) Nesting depth|F1: No children|`{"_100": {"range": 60}}`|
|||F2: Child under a top-level code **(Base)**|`{"_100": {"range": 60, "_110": {...}}}`|
|||F3: Grandchild under a child|`{"_100": {"range": 60, "_110": {"_120": {...}}}}`|
|`tower_data` (child node)|G) Child's own fields|G1: Overrides a scalar **(Base)**|`"_110": {"range": 70}`|
|||G2: Empty node|`"_110": {}`|
|||G3: Overrides one key inside a nested dict|`"_110": {"attacks": {"rate": 2}}`|
|`tower_data`|H) Siblings|H1: Single child **(Base)**|one `_110` under `_100`|
|||H2: Two children under one parent|`_110` and `_120` under `_100`|
|||H3: Two top-level upgrades|`_100` and `_010` at the top level|
|`tower_data`|I) Input is empty|I1: Non-empty **(Base)**|`{"_100": {...}}`|
|||I2: Empty|`{}`|

Base case: E1, F2, G1, H1, I1

Base input (T1):

```python
tower_data = {
    "_100": {
        "range": 60,
        "attacks": {"rate": 1, "count": 3},
        "_110": {"range": 70},
    }
}
```

Excluded or reduced combinations:

- I2 has no nodes, so E, F, G and H are irrelevant; it is tested once.
- F1 has no child, so G and H are irrelevant there; it is tested once.
- G2 and G3 only differ from G1 when a child exists (F2 or F3), which holds at base.
- F3 reuses the base child and adds one grandchild, so the grandchild's own fields stay `{"range": 80}`; varying them as well would repeat G.
- H3 has no shared parent, so it checks that a top-level node does not inherit from another top-level node.

### Base Choice Coverage

| BCC Test | E | F | G | H | I | Oracle | Test Name |
|---|---|---|---|---|---|---|---|
| T1 | E1 | F2 | G1 | H1 | I1 | returns `{"_100": {"range": 60, "attacks": {"rate": 1, "count": 3}}, "_110": {"range": 70, "attacks": {"rate": 1, "count": 3}}}`; the input still equals its original value | `test_resolve_all_codes_child_overrides_scalar` |
| T2 | E2 | F2 | G1 | H1 | I1 | with `"range": 50` added at the top level: same result as T1, `"range" not in result` | `test_resolve_all_codes_ignores_non_code_key` |
| T3 | E3 | F2 | G1 | H1 | I1 | with `"_01": {"range": 3}` added at the top level: same result as T1, `"_01" not in result` | `test_resolve_all_codes_ignores_malformed_key` |
| T4 | E1 | F1 | G1 | H1 | I1 | `resolve_all_codes({"_100": {"range": 60}})` returns `{"_100": {"range": 60}}` | `test_resolve_all_codes_no_children` |
| T5 | E1 | F3 | G1 | H1 | I1 | with `"_120": {"range": 80}` added inside `_110`: result has `"_120" == {"range": 80, "attacks": {"rate": 1, "count": 3}}` and still has the T1 `_100` and `_110` | `test_resolve_all_codes_grandchild_inherits_chain` |
| T6 | E1 | F2 | G2 | H1 | I1 | with `"_110": {}`: `result["_110"] == {"range": 60, "attacks": {"rate": 1, "count": 3}}` | `test_resolve_all_codes_empty_child_inherits_all` |
| T7 | E1 | F2 | G3 | H1 | I1 | with `"_110": {"attacks": {"rate": 2}}`: `result["_110"] == {"range": 60, "attacks": {"rate": 2, "count": 3}}` | `test_resolve_all_codes_child_partial_dict_merge` |
| T8 | E1 | F2 | G1 | H2 | I1 | with a second child `"_120": {"attacks": {"count": 9}}`: `result["_120"] == {"range": 60, "attacks": {"rate": 1, "count": 9}}` and `result["_110"]` equals T1's; `result["_100"]` is unchanged | `test_resolve_all_codes_siblings_independent` |
| T9 | E1 | F2 | G1 | H3 | I1 | with `"_010": {"range": 40}` added at the top level: `result["_010"] == {"range": 40}`; the other entries equal T1 | `test_resolve_all_codes_top_level_siblings` |
| T10 | E1 | F2 | G1 | H1 | I2 | `resolve_all_codes({})` returns `{}` | `test_resolve_all_codes_empty` |

Oracle checks shared by all cases: the input dict equals a deep copy taken before the call, and changing a nested value in one result entry does not change any other entry (results are not aliased).

Regression: resolving the real Super Monkey module must give 64 codes, the same set as `data.csv`; that check needs a trimmed fixture under `tests/fixtures/` and sits outside this table.
