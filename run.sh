#!/usr/bin/env bash
# Activate .venv and launch ten-9.
# Pass through any args (e.g. `./run.sh --list-devices`).

set -euo pipefail

if [ ! -f ".venv/bin/activate" ]; then
    echo "Virtual environment not found. Run ./setup.sh first."
    exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python ten9.py "$@"
