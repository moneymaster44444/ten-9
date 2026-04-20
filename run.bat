@echo off
REM Activate .venv and launch ten-9.
REM Pass through any args (e.g. `run.bat --list-devices`).

if not exist ".venv\Scripts\activate.bat" (
    echo Virtual environment not found. Run setup.bat first.
    exit /b 1
)

call ".venv\Scripts\activate.bat"
python ten9.py %*
