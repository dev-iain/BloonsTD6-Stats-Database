---
name: etl-refresh
description: Re-fetch a tower's stats from the Bloons wiki, regenerate data.json and data.csv, and diff row counts. Use when tower data needs updating or a new tower is added.
disable-model-invocation: true
argument-hint: "[tower name, default Super Monkey]"
---

# ETL refresh

Tower: `$ARGUMENTS` (default `Super Monkey`).

1. Record the current row count: `wc -l data.csv`.
2. Fetch and resolve (network access happens only here):
   `uv run python -c "from btd6.etl.fetch import write_resolved_json; write_resolved_json('<tower>')"`
3. Rebuild the CSV: `uv run python -c "from btd6.etl.extract import export_csv; export_csv()"`
4. Compare: `git diff --stat data.csv` and row counts. Super Monkey should have 64 upgrade rows; report anything else.
5. If a DB loader exists, rebuild the database and run `uv run pytest`.
6. Report changed rows only, not the full file.
