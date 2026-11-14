---
name: tdd-cycle
description: Red-green-refactor workflow for any new btd6 feature or bug fix. Use at the start of every implementation task in this repo.
---

# TDD cycle

1. **Red**: delegate to the `test-writer` agent with the requirement (or ISP table). Run `uv run pytest -x` and confirm the new test fails for the right reason.
2. **Green**: delegate to the `implementer` agent to make it pass with the minimum code. Do not edit tests to fit the code.
3. **Refactor**: run `uv run ruff check . && uv run ruff format .`. Any function over 30 lines gets helpers with descriptive names (4+ character variable names, type hints, no organizing comments).
4. **Review**: run the `style-reviewer` agent on the diff.
5. Full `uv run pytest` must be green before commit. Run the `mutation-checker` agent when a module is feature-complete.
