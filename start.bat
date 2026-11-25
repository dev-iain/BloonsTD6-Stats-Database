@echo off
rem Start the BTD6 advisor. Extra options go to "btd6 start" (--game, --refresh, --no-browser, --port N).
cd /d "%~dp0"
where uv >nul 2>nul || (echo uv is not installed. See https://docs.astral.sh/uv/getting-started/installation/ & pause & exit /b 1)
uv sync --quiet || (pause & exit /b 1)
uv run python -m btd6 start %*
if errorlevel 1 pause
