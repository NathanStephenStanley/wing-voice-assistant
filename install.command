#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
# Prefer a Python version with prebuilt speech/ONNX wheels. Python 3.14 may not
# have a compatible onnxruntime wheel yet, so avoid silently selecting it.
PYTHON_BIN=""
for candidate in python3.12 python3.11 python3.13; do
  if command -v "$candidate" >/dev/null 2>&1; then PYTHON_BIN="$(command -v "$candidate")"; break; fi
done
if [ -z "$PYTHON_BIN" ]; then
  echo "Python 3.11, 3.12, or 3.13 is required. Install Python 3.12, then rerun this script." >&2
  exit 1
fi
"$PYTHON_BIN" - <<'PY'
import sys
if not ((3, 11) <= sys.version_info[:2] <= (3, 13)):
    raise SystemExit("Python 3.11–3.13 required; Python 3.12 is recommended.")
print("Using", sys.version)
PY
"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install --upgrade pip wheel
.venv/bin/python -m pip install -r requirements.txt
mkdir -p assets logs
for f in app iem-profiles tool-map; do
  if [ ! -f "config/${f}.json" ]; then cp "config/${f}.example.json" "config/${f}.json"; fi
done
cat <<'MSG'

Installed Python dependencies and created local config files.
Next:
  1. Set DVS device names in config/app.json.
  2. Configure the existing WING MCP gateway path and exact tool mappings.
  3. Run .venv/bin/python -m wing_voice.cli devices
  4. Read README.md and verify routing before enabling any writes.
MSG
