"""Stop hook: keep Claude working while the test suite is failing."""

from __future__ import annotations

import json
import subprocess
import sys

NO_TESTS_COLLECTED = 5
TAIL_LINES = 30


def main() -> int:
    payload = json.load(sys.stdin)
    if payload.get("stop_hook_active"):
        return 0
    result = subprocess.run(["uv", "run", "pytest", "-q", "-x"], capture_output=True, text=True)
    if result.returncode in (0, NO_TESTS_COLLECTED):
        return 0
    tail = "\n".join(result.stdout.splitlines()[-TAIL_LINES:])
    print(f"Tests are failing; fix them before stopping:\n{tail}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
