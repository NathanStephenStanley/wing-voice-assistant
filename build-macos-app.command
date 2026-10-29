#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This build script must be run on macOS. It cannot create a genuine macOS .app on another OS." >&2
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  ./install.command
fi
.venv/bin/python -m pip install --upgrade pyinstaller
.venv/bin/python scripts/generate_icon.py
rm -rf build dist
.venv/bin/pyinstaller \
  --icon assets/AppIcon.icns \
  --noconfirm --clean --windowed \
  --name "WING Voice Assistant" \
  --osx-bundle-identifier "local.wing.voiceassistant" \
  --add-data "wing_voice:assistant_project/wing_voice" \
  --add-data "config:assistant_project/config" \
  --add-data "assets:assistant_project/assets" \
  --add-data "tests:assistant_project/tests" \
  --add-data "README.md:assistant_project" \
  --add-data "requirements.txt:assistant_project" \
  --add-data "install.command:assistant_project" \
  --add-data "run.command:assistant_project" \
  --add-data "gui.command:assistant_project" \
  wing_voice/gui.py
cat <<'MSG'

Built: dist/WING Voice Assistant.app
Move it to Applications if you like. On first launch it copies its editable project
files into ~/Library/Application Support/WING Voice Assistant/project. Then open
that folder's install.command in Terminal to install the voice/audio dependencies.
MSG
