---
name: isp-tables
description: Correct procedure for creating input space partitioning (ISP) tables for all tests. 
---

# Internal Input Space Partitioning Process

For each operation, internally identify characteristics that may affect its behavior. These may include:

- Individual parameter properties
  - Null vs non-null, enum values, numeric boundaries 
- Receiver-object state before the call
  - Current state of class, state of contained objects, whether object is in valid state
- Relationship between inputs
  - Parameter vs parameter, such as same object passed twice
- Functional outcome / behavior
  - Should this method return null/false or throw an error?
  - Does this method interact with other methods? 
  - How would the parameters affect function? What does the outcome of the method look like with these different characteristics / parameters in conjunction?
- Code structure
  - Does the method call a parameter before it has been null-checked?

## Guidelines

1. Do not include ISP inputs that are infeasible. 
2. Include functional-based modeling; i.e, do not just cover for individual parameters. Also create tests and oracles that result from the combination of parameters to model the intended behavior and function of the method.
3. Input values should always be real tangible inputs, when possible. This makes BCC oracle modeling substantially easier. This can be seen in the examples provided.

## Writing ISP tables

## ISP Format

Write the table in markdown, in the test/isp-tables/ directory. 
Use a table in the following format:

| Variable   | Characteristic    | Partition/Block | Representative Value |
|------------|-------------------|-----------------|----------------------|
| V1: [Name] | C1: [Description] | C1-B1 (Base)    | [Value 1]            |
| V1: [Name] | C1: [Description] | C1-B2           | [Value 2]            |
| V2: [Name] | C2: [Description] | C2-B1 (Base)    | [Value 3]            |
| V2: [Name] | C2: [Description] | C2-B2           | [Value 4]            |

# Internal Base Choice Coverage Process

For each constructor or method:

1. Select exactly one base block for every characteristic (the block marked `(Base)` in the ISP table).
2. Create exactly one all-base test requirement using all selected base blocks.
3. Create one further requirement per non-base block, changing only that block and keeping every other characteristic at its base.
4. Skip any branches that can't be reached from valid or testable inputs.
5. For the `Expected result` column, include real output values that can be seen directly when running the code. When applicable, also clarify which method returns the expected result; for example, if the BCC table is for `setSalary`, an expected result value would look like `getSalary() returns 0.0`.

## BCC Format

Write the table in markdown directly below the ISP table it is derived from. Use a table in the following format:

| Case ID | C1 selection | C2 selection | Changed characteristic | Expected result |
| ------- | ------------ | ------------ | ---------------------- | --------------- |
| BCC-1   | C1-B1        | C2-B1        | None — All Base        | [Result]        |
| BCC-2   | C1-B2        | C2-B1        | C1                     | [Result]        |
| BCC-3   | C1-B1        | C2-B2        | C2                     | [Result]        |

Perform the selection steps internally. Do not repeat the partitions, base blocks, combinations, or internal validation in the chat response; the tables in the file are the deliverable.