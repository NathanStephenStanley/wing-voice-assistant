#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Run ./install.command first to install dependencies." >&2
  exit 1
fi
exec .venv/bin/python -m wing_voice.gui
