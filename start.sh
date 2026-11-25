#!/usr/bin/env sh
# Start the BTD6 advisor: install dependencies, build the database on first run,
# serve the web UI and open it in the browser. Extra options go to "btd6 start"
# (--game, --refresh, --no-browser, --port N).
set -e
cd "$(dirname "$0")"
if ! command -v uv >/dev/null 2>&1; then
    echo "uv is not installed. See https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi
uv sync --quiet
exec uv run python -m btd6 start "$@"
