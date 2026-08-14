@echo off
cd /d "%~dp0"
where uv >nul 2>nul || (echo uv not found - install from https://docs.astral.sh/uv/ && pause && exit /b 1)
if not exist .env copy .env.example .env >nul
uv sync --all-groups
uv run playwright install chromium
uv run streamlit run app.py --server.port 8511
pause
