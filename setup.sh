#!/usr/bin/env bash
# ============================================================
#  ten-9 setup (Linux / macOS)
# ============================================================
#  - Creates .venv and installs Python dependencies.
#  - Downloads the Piper binary and default GLaDOS voice model.
#  - Copies config.EXAMPLE.toml -> config.toml on first run.
#
#  To pin a different Piper or voice model, edit the URLs below.
# ============================================================

set -euo pipefail

# -- Piper binary (rhasspy/piper, MIT-licensed, maintenance mode) --
PIPER_VERSION="2023.11.14-2"

case "$(uname -s)-$(uname -m)" in
    Linux-x86_64)   PIPER_ARCHIVE="piper_linux_x86_64.tar.gz" ;;
    Linux-aarch64)  PIPER_ARCHIVE="piper_linux_aarch64.tar.gz" ;;
    Linux-armv7l)   PIPER_ARCHIVE="piper_linux_armv7l.tar.gz" ;;
    Darwin-x86_64)  PIPER_ARCHIVE="piper_macos_x64.tar.gz" ;;
    Darwin-arm64)   PIPER_ARCHIVE="piper_macos_aarch64.tar.gz" ;;
    *)
        echo "ERROR: unsupported platform $(uname -s)-$(uname -m)"
        echo "See https://github.com/rhasspy/piper/releases for available binaries."
        exit 1
        ;;
esac
PIPER_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/${PIPER_ARCHIVE}"

# -- GLaDOS voice model (DavesArmoury, CC-BY-4.0) --
MODEL_URL="https://huggingface.co/DavesArmoury/GLaDOS_TTS/resolve/main/glados_piper_medium.onnx"
MODEL_JSON_URL="https://huggingface.co/DavesArmoury/GLaDOS_TTS/resolve/main/glados_piper_medium.onnx.json"

# ------------------------------------------------------------
#  1. Python + venv + dependencies
# ------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found. Install Python 3.11 or newer."
    exit 1
fi
echo "Using $(python3 --version)"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv ..."
    python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "Installing Python dependencies ..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# ------------------------------------------------------------
#  2. Piper binary
# ------------------------------------------------------------
if [ ! -x "piper/piper" ] && [ ! -x "piper/piper.exe" ]; then
    mkdir -p piper
    echo "Downloading Piper ${PIPER_VERSION} for $(uname -s)-$(uname -m) ..."
    curl -L --fail -o piper.tar.gz "${PIPER_URL}"
    echo "Extracting Piper ..."
    tar -xzf piper.tar.gz -C piper --strip-components=1
    rm -f piper.tar.gz
else
    echo "Piper already installed -- skipping download."
fi

# ------------------------------------------------------------
#  3. GLaDOS voice model
# ------------------------------------------------------------
mkdir -p piper/models
if [ ! -f "piper/models/glados_piper_medium.onnx" ]; then
    echo "Downloading GLaDOS voice model ..."
    curl -L --fail -o "piper/models/glados_piper_medium.onnx" "${MODEL_URL}"
    curl -L --fail -o "piper/models/glados_piper_medium.onnx.json" "${MODEL_JSON_URL}"
else
    echo "GLaDOS model already present -- skipping download."
fi

# ------------------------------------------------------------
#  4. Config file
# ------------------------------------------------------------
if [ ! -f "config.toml" ]; then
    echo "Copying config.EXAMPLE.toml -> config.toml"
    cp config.EXAMPLE.toml config.toml
fi

echo
echo "============================================================"
echo "  Setup complete."
echo "  1. Edit config.toml to match your setup."
echo "  2. Run './run.sh --list-devices' to see audio device names."
echo "  3. Run './run.sh' to start ten-9."
echo "     (Linux: global hotkeys via the 'keyboard' library require root)"
echo "============================================================"
