---
name: add-cli-command
description: Pattern for adding a CLI subcommand to the btd6 CLI together with its tests. Use when adding or changing CLI behavior.
---

# Add a CLI command

- The CLI is `argparse` subparsers in `btd6/cli.py`, invoked as `python -m btd6 <command>`. It stays a thin layer: parse args, call a function in `btd6.query`, print a pandas table. No SQL or business logic in the CLI.
- Test first: write the CLI test (capsys or subprocess) against an in-memory/temporary DB before the command exists. See `.claude/rules/testing.md`.
- One function per subcommand handler, each under 30 lines; shared argument definitions go in helpers.
- Example target: `python -m btd6 search --can-pop-lead --min-pierce 5 --sort damage`.
