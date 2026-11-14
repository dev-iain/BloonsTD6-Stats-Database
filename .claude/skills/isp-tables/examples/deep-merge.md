# Example: `deep_merge(base: dict, override: dict) -> dict`

Take the function `deep_merge(base, override)` in `btd6/etl/fetch.py`, whose ISP is provided below. First, we use interface-based modeling; we know that the function takes in `base` and `override`, thus we model the characteristics of each key in `override`, since the override is what is applied onto the base. To determine important characteristics, we first fixate on the function of the code: an upgrade inherits all stats from its parent upgrade, and only the fields it changes are overwritten. We know that what happens to a key depends on what `override` holds for it, thus we first have to model the `override` value type (scalar versus nested dict) because it directly influences whether a value is replaced or merged. We are also told that keys matching `_NNN` are crosspath children and must never be copied as fields, thus we also model this characteristic so child upgrades do not leak into their parent's stats. Because the function must overlay onto a copy, we must also model whether the caller's `base` is left untouched afterward; this is a functional outcome, not a parameter property. Finally, whether a nested dict is merged or replaced depends on the interaction between `base` and `override`: both must hold a dict for the same key. So we model the combination of the type of `base[key]` and the type of `override[key]`, rather than each on its own.

## ISP

| Parameter | Characteristic | Partition | Value |
|---|---|---|---|
| `override` | A) Value type for a key | A1: Scalar | `{"range": 60}` |
||| A2: Nested dict (Base) | `{"attacks": {"rate": 0.5}}` |
| `override` | B) Key is a crosspath code | B1: Normal field (Base) | `{"range": 60}` |
||| B2: Matches `_NNN` | `{"_012": {"range": 90}}` |
| `base` & `override` | C) Type of `base[key]` vs `override[key]` | C1: Key absent in `base` | base `{}`, override `{"range": 60}` |
||| C2: Both dicts (merge) (Base) | base `{"attacks": {"rate": 1.0, "count": 1}}`, override `{"attacks": {"rate": 0.5}}` -> `{"rate": 0.5, "count": 1}` |
||| C3: Dict in `base`, scalar in `override` (replace) | base `{"attacks": {"rate": 1.0}}`, override `{"attacks": 0}` |
||| C4: Scalar in `base`, dict in `override` (replace) | base `{"attacks": 0}`, override `{"attacks": {"rate": 0.5}}` |
| `base` | D) `base` after the call | D1: Unchanged (Base) | `base == {"attacks": {"rate": 1.0}}` after merging override `{"attacks": {"rate": 0.5}}` |
| `override` | E) Override contents | E1: Non-empty (Base) | `{"range": 60}` |
||| E2: Empty | `{}` -> result equals `base`, as a different object |

Feasibility notes: B2 combined with C2 to C4 is infeasible (crosspath keys are always skipped before the type check), so B2 is tested once alone. A hypothesis property is a good fit here: for any `base`, `deep_merge(base, {})` equals `base`, and `base` is never mutated.

## Base Choice Coverage

Characteristic A is not varied independently: it is determined by C (A1 is the override side of C1 and C3, A2 is the override side of C2 and C4), so A's blocks are covered by the C cases. D has a single block and is checked in the `Expected result` of every case. BCC is therefore taken over B, C and E. A crosspath key (B2) and an empty override (E2) have no key to compare, so C does not apply to them; the C selection is kept at base only as a label.

| Case ID | B selection | C selection | E selection | Changed characteristic | Expected result |
| ------- | ----------- | ----------- | ----------- | ---------------------- | --------------- |
| BCC-1 | B1 | C2 | E1 | None — All Base | `deep_merge({"attacks": {"rate": 1.0, "count": 1}}, {"attacks": {"rate": 0.5}})` returns `{"attacks": {"rate": 0.5, "count": 1}}`; `base` still equals `{"attacks": {"rate": 1.0, "count": 1}}` |
| BCC-2 | B1 | C1 | E1 | C | `deep_merge({}, {"range": 60})` returns `{"range": 60}` |
| BCC-3 | B1 | C3 | E1 | C | `deep_merge({"attacks": {"rate": 1.0}}, {"attacks": 0})` returns `{"attacks": 0}` |
| BCC-4 | B1 | C4 | E1 | C | `deep_merge({"attacks": 0}, {"attacks": {"rate": 0.5}})` returns `{"attacks": {"rate": 0.5}}` |
| BCC-5 | B2 | C2 | E1 | B | `deep_merge({"range": 50}, {"_012": {"range": 90}})` returns `{"range": 50}`; `"_012" not in result` |
| BCC-6 | B1 | C2 | E2 | E | `deep_merge({"range": 50}, {})` returns `{"range": 50}`; `result is not base` |

BCC-5 and BCC-6 do not use the C2 inputs literally, since a crosspath key or empty override has nothing to merge; their C selection is the base label only. This is the "branch that can't be reached" case from the BCC rules: the combination of B2 or E2 with a real C2 merge is infeasible.
