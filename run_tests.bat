@echo off
if not exist .venv\Scripts\pytest.exe (
    echo Error: .venv virtual environment not found.
    pause
    exit /b 1
)
.\.venv\Scripts\pytest.exe -v %*
