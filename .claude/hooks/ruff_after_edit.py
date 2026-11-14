"""PostToolUse hook: format and lint any edited Python file, feeding violations back to Claude."""

from __future__ import annotations

import json
import subprocess
import sys


def main() -> int:
    payload = json.load(sys.stdin)
    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path.endswith(".py"):
        return 0
    subprocess.run(["uv", "run", "ruff", "format", file_path], capture_output=True)
    result = subprocess.run(
        ["uv", "run", "ruff", "check", "--fix", file_path], capture_output=True, text=True
    )
    if result.returncode == 0:
        return 0
    print(result.stdout + result.stderr, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
