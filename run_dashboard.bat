@echo off
echo ===================================================
echo Starting Operon Glassmorphic Web Dashboard in .venv
echo ===================================================
if not exist .venv\Scripts\uvicorn.exe (
    echo Error: .venv virtual environment not found.
    echo Please run 'python -m venv .venv' and 'pip install -r requirements.txt'
    pause
    exit /b 1
)
.\.venv\Scripts\uvicorn.exe ui.app:app --host 127.0.0.1 --port 8000 --reload
