"""PreToolUse hook: protect generated data and keep wiki access inside the etl-refresh skill."""

from __future__ import annotations

import json
import re
import sys

BLOCKED_PATTERNS = (
    (r"\brm\b.*(data\.json|\.db\b)", "refusing to delete data.json or a .db file"),
    (r"\b(curl|wget)\b.*bloonswiki", "fetch wiki data through the etl-refresh skill instead"),
)


def main() -> int:
    payload = json.load(sys.stdin)
    command = payload.get("tool_input", {}).get("command", "")
    for pattern, reason in BLOCKED_PATTERNS:
        if re.search(pattern, command):
            print(f"Blocked: {reason}.", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
