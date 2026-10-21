@echo off
if not exist .venv\Scripts\python.exe (
    echo Error: .venv virtual environment not found.
    pause
    exit /b 1
)
.\.venv\Scripts\python.exe cli.py %*
