@echo off
REM ============================================================
REM  ten-9 setup (Windows)
REM ============================================================
REM  - Creates .venv and installs Python dependencies.
REM  - Downloads the Piper binary and default GLaDOS voice model.
REM  - Copies config.EXAMPLE.toml -^> config.toml on first run.
REM
REM  To pin a different Piper or voice model, edit the URLs below.
REM ============================================================

setlocal

REM -- Piper binary (rhasspy/piper, MIT-licensed, maintenance mode) --
set "PIPER_VERSION=2023.11.14-2"
set "PIPER_ARCHIVE=piper_windows_amd64.zip"
set "PIPER_URL=https://github.com/rhasspy/piper/releases/download/%PIPER_VERSION%/%PIPER_ARCHIVE%"

REM -- GLaDOS voice model (DavesArmoury, CC-BY-4.0) --
set "MODEL_URL=https://huggingface.co/DavesArmoury/GLaDOS_TTS/resolve/main/glados_piper_medium.onnx"
set "MODEL_JSON_URL=https://huggingface.co/DavesArmoury/GLaDOS_TTS/resolve/main/glados_piper_medium.onnx.json"

REM ------------------------------------------------------------
REM  1. Python + venv + dependencies
REM ------------------------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python is not on your PATH.
    echo Install Python 3.11 or newer from https://www.python.org/ and re-run.
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo Using Python %PYVER%

if not exist ".venv" (
    echo Creating virtual environment in .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: failed to create virtual environment.
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"
echo Installing Python dependencies ...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    exit /b 1
)

REM ------------------------------------------------------------
REM  2. Piper binary
REM ------------------------------------------------------------
if not exist "piper\piper.exe" (
    if not exist "piper" mkdir "piper"
    echo Downloading Piper %PIPER_VERSION% ...
    curl -L --fail -o "piper.zip" "%PIPER_URL%"
    if errorlevel 1 (
        echo ERROR: failed to download Piper from %PIPER_URL%
        exit /b 1
    )
    echo Extracting Piper ...
    REM The zip's top-level folder is "piper/", so strip it and extract into our piper/.
    tar -xf "piper.zip" -C "piper" --strip-components=1
    if errorlevel 1 (
        echo ERROR: failed to extract piper.zip
        exit /b 1
    )
    del "piper.zip"
) else (
    echo Piper already installed at piper\piper.exe -- skipping download.
)

REM ------------------------------------------------------------
REM  3. GLaDOS voice model
REM ------------------------------------------------------------
if not exist "piper\models" mkdir "piper\models"
if not exist "piper\models\glados_piper_medium.onnx" (
    echo Downloading GLaDOS voice model ...
    curl -L --fail -o "piper\models\glados_piper_medium.onnx" "%MODEL_URL%"
    if errorlevel 1 (
        echo ERROR: failed to download GLaDOS model.
        exit /b 1
    )
    curl -L --fail -o "piper\models\glados_piper_medium.onnx.json" "%MODEL_JSON_URL%"
    if errorlevel 1 (
        echo ERROR: failed to download GLaDOS model JSON.
        exit /b 1
    )
) else (
    echo GLaDOS model already present -- skipping download.
)

REM ------------------------------------------------------------
REM  4. Config file
REM ------------------------------------------------------------
if not exist "config.toml" (
    echo Copying config.EXAMPLE.toml -^> config.toml
    copy /Y "config.EXAMPLE.toml" "config.toml" >nul
)

echo.
echo ============================================================
echo  Setup complete.
echo  1. Edit config.toml to match your setup.
echo  2. Run `run.bat --list-devices` to see audio device names.
echo  3. Run `run.bat` to start ten-9.
echo ============================================================
endlocal
