# Example: `deep_merge(base: dict, override: dict) -> dict`

Take the function `deep_merge(base, override)` in `btd6/etl/fetch.py`, whose ISP is provided below. First, we use interface-based modeling; we know that the function takes in `base` and `override`, thus we model the characteristics of each key in `override`, since the override is what is applied onto the base. To determine important characteristics, we first fixate on the function of the code: an upgrade inherits all stats from its parent upgrade, and only the fields it changes are overwritten. What happens to a key depends on what `override` holds for it, thus we model the type of `override[key]` (scalar versus nested dict), because it directly influences whether a value is replaced or merged. Whether a nested dict is merged or replaced also depends on what `base` holds for the same key, so we model the state of `base[key]` as its own characteristic; the functional behavior then comes from combining the two, not from either alone. We are also told that keys matching `_NNN` are crosspath children and must never be copied as fields, thus we model whether the key is a crosspath code so child upgrades do not leak into their parent's stats. Finally, we model whether `override` is empty, since there is then no key to compare and the result must still be a copy of `base`. Whether the caller's `base` is left untouched is a functional outcome, so it is checked in the oracle rather than modeled as a characteristic.

## ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`override`|A) Type of `override["attacks"]`|A1: Scalar|`0`|
|||A2: Nested dict|`{"rate": 0.5}`|
|`base`|B) State of `base["attacks"]`|B1: Absent|`{}`|
|||B2: Dict|`{"rate": 1.0, "count": 1}`|
|||B3: Scalar|`0`|
|`override`|C) Key is a crosspath code|C1: Normal field|`{"attacks": {"rate": 0.5}}`|
|||C2: Key matches `_NNN`|`{"_012": {"range": 90}}`|
|`override`|D) Override is empty|D1: Non-empty|`{"attacks": {"rate": 0.5}}`|
|||D2: Empty|`{}`|

Base case: A2, B2, C1, D1

Feasibility notes: C2 and D2 make A and B irrelevant (a crosspath key is skipped before the type check, and an empty override has no key), so each is tested once with A and B at base. Every A x B combination is otherwise feasible. A hypothesis property is a good fit here: for any `base`, `deep_merge(base, {})` equals `base`, and `base` is never mutated.

## Base Choice Coverage

| BCC Test | A | B | C | D | Oracle | Test Name |
|---|---|---|---|---|---|---|
| T1 | A2 | B2 | C1 | D1 | `deep_merge({"attacks": {"rate": 1.0, "count": 1}}, {"attacks": {"rate": 0.5}})` returns `{"attacks": {"rate": 0.5, "count": 1}}`; `base` still equals `{"attacks": {"rate": 1.0, "count": 1}}` | `test_deep_merge_both_dicts` |
| T2 | A1 | B2 | C1 | D1 | `deep_merge({"attacks": {"rate": 1.0, "count": 1}}, {"attacks": 0})` returns `{"attacks": 0}` | `test_deep_merge_scalar_replaces_dict` |
| T3 | A2 | B1 | C1 | D1 | `deep_merge({}, {"attacks": {"rate": 0.5}})` returns `{"attacks": {"rate": 0.5}}` | `test_deep_merge_key_absent_in_base` |
| T4 | A2 | B3 | C1 | D1 | `deep_merge({"attacks": 0}, {"attacks": {"rate": 0.5}})` returns `{"attacks": {"rate": 0.5}}` | `test_deep_merge_dict_replaces_scalar` |
| T5 | A2 | B2 | C2 | D1 | `deep_merge({"range": 50}, {"_012": {"range": 90}})` returns `{"range": 50}`; `"_012" not in result` | `test_deep_merge_crosspath_key` |
| T6 | A2 | B2 | C1 | D2 | `deep_merge({"range": 50}, {})` returns `{"range": 50}`; `result is not base` | `test_deep_merge_empty_override` |

T5 and T6 do not use the base A and B inputs literally, since a crosspath key or empty override has nothing to merge; their A and B selections are base labels only.
