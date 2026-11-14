---
name: isp-tables
description: Correct procedure for creating input space partitioning (ISP) tables and base choice coverage (BCC) tables for all tests.
---

# Internal Input Space Partitioning Process

For each constructor or method, internally identify the characteristics that change its behavior. Consider:

- Individual parameter properties
  - Null vs non-null, enum values, numeric boundaries
- Receiver-object state before the call
  - State of the class, state of contained objects, whether the object is in a valid state
- Relationship between inputs
  - Parameter vs parameter, or parameter vs `this`, such as the same object passed twice or a name that matches `this`
- Functional outcome / behavior
  - Should the method return null/false or throw an error?
  - Does the method interact with other methods?
  - How do the parameters, in conjunction, change what the method produces?
- Code structure
  - Does the method use a parameter before it has been null-checked?

## Guidelines

1. A characteristic is one aspect of the input that changes the behavior of the method under test. Do not include a characteristic that cannot change the outcome (for example, a field the method never reads).
2. The blocks of a characteristic must be mutually exclusive, and together they must cover every case that characteristic can take. One input falls in exactly one block of each characteristic.
3. A characteristic may describe a relationship (for example, "`o`'s relationship to `this`") instead of a single parameter. Use this to model the behavior of the method, not just each parameter on its own.
4. Do not make a characteristic out of something already determined by other characteristics (a combination of them, or the expected output). Check that in the oracle instead.
5. Do not include blocks that are infeasible.
6. Representative values must be real, tangible inputs whenever possible, so oracles can be read off directly. See the examples.

# Writing ISP tables

Write the table in markdown, in the `test/isp-tables/` directory, one section per constructor or method, with the signature and a one-line description of its behavior above the table.

- Characteristics are lettered: `A)`, `B)`, `C)`, …
- The blocks of a characteristic are numbered with that letter: `A1`, `A2`, `A3`, …
- Every row is exactly one block. The `Partition` cell is the letter and number, a colon, and a short description of the circumstance being tested (for example, `A1: Project names are Equal`). The `Value` cell is the concrete input for that block.
- The `Parameter` and `Characteristic` cells are written on the first row of a characteristic and left blank on its remaining rows.
- State the base block of every characteristic on a `Base case:` line below the table.

```markdown
## equals
```java
boolean equals(Object o)
```
Two Project instances are equal if and only if their names match.
### ISP
|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`o`|A) Relationship to `this`|A1: Project names are Equal|`o.name` = `"Project"`|
|||A2: Project names are not Equal|`o.name` = `"Other"`|
|||A3: Null|`null`|
|||A4: `o` is not Project|`"String"`|
|`this` (state: projects)|B) Number of projects|B1: None|`{}`|
|||B2: One or more|`{p}`|

Base case: A1, B2
```

# Internal Base Choice Coverage Process

For each constructor or method:

1. Select exactly one base block for every characteristic.
2. Create exactly one all-base test (T1) using every base block.
3. Create one further test per non-base block, changing only that block and keeping every other characteristic at its base block.
4. Skip any test that cannot be reached from valid or testable inputs. If two characteristics can only be varied together, add one extra test for that combination and say it is not a BCC test.
5. For the `Oracle` column, give real output values that can be seen directly when running the code. When applicable, say which method returns the value; for a BCC table for `setSalary`, an oracle would look like `getSalary()` returns `0.0`.

# Writing BCC tables

Write the table in markdown directly below the ISP table it is derived from, with one column per characteristic that is varied, holding the selected block (`A1`, `B2`, …):

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B2 | [Result] | [test name] |
| T2 | A2 | B2 | [Result] | [test name] |
| T3 | A1 | B1 | [Result] | [test name] |

## Test names

A test name is `test`, then the name of the method being tested, then a descriptor of the case. Testing a `null` input for a function `sum` is `testSumNull()`. In Python, use snake case: `test_sum_null`. For a constructor, use the class name in place of the method name.

Perform the selection steps internally. Do not repeat the partitions, base blocks, combinations, or internal validation in the chat response; the tables in the file are the deliverable.
