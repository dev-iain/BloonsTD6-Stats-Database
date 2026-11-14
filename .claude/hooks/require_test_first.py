"""PreToolUse hook: block edits to btd6/ source until a test file has changed (TDD).

Set BTD6_SKIP_TDD=1 to bypass for refactors or scaffolding.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys


def test_files_changed() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", "tests"], capture_output=True, text=True
    )
    changed = [line for line in result.stdout.splitlines() if line.endswith(".py")]
    return any(not line.endswith("__init__.py") for line in changed)


def main() -> int:
    payload = json.load(sys.stdin)
    file_path = payload.get("tool_input", {}).get("file_path", "")
    if "/btd6/" not in file_path or os.environ.get("BTD6_SKIP_TDD"):
        return 0
    if test_files_changed():
        return 0
    print(
        "TDD guard: write a failing test in tests/ before editing btd6/ source "
        "(delegate to the test-writer agent, or set BTD6_SKIP_TDD=1 to bypass).",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
