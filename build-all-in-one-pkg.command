#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != "Darwin" ]]; then echo "Run this on the Mac that will build the installer. Apple .app/.pkg builds cannot be produced on Linux." >&2; exit 1; fi
ARCH="$(uname -m)"
if [[ "$ARCH" != "arm64" && "$ARCH" != "x86_64" ]]; then echo "Unsupported build architecture: $ARCH" >&2; exit 1; fi
PY=""
for c in python3.12 python3.11 python3.13; do if command -v "$c" >/dev/null 2>&1; then PY="$(command -v "$c")"; break; fi; done
if [[ -z "$PY" ]]; then echo "A build-time Python 3.11–3.13 is required on the build Mac; the recipient will not need Python." >&2; exit 1; fi
"$PY" -m venv .build-venv
B=.build-venv/bin/python
"$B" -m pip install --upgrade pip wheel
"$B" -m pip install -r requirements.txt pyinstaller
mkdir -p assets
# Open-source Vosk English model; downloaded during build and embedded in the installer.
if [[ ! -f assets/vosk-model-small-en-us-0.15/am/final.mdl ]]; then
  curl -L --fail --retry 3 https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -o /tmp/vosk-model-small-en-us-0.15.zip
  unzip -q -o /tmp/vosk-model-small-en-us-0.15.zip -d assets
fi
# Download and bundle the Whisper base.en model at build time, so first launch is offline.
if [[ ! -f assets/whisper-base.en/model.bin ]]; then
  "$B" - <<'PY'
from faster_whisper.utils import download_model
from pathlib import Path
p=download_model("base.en", output_dir=str(Path("assets/whisper-base.en").resolve()))
print("Bundled Whisper model:", p)
PY
fi
# Frozen runtime contains Python and all Python/native wheel dependencies.
rm -rf build dist
"$B" -m PyInstaller --noconfirm --clean --onefile --name wing-voice-runtime \
  --collect-all faster_whisper --collect-all ctranslate2 --collect-all av \
  --collect-all vosk --collect-all sounddevice --collect-all scipy --collect-all numpy \
  --add-data "assets/vosk-model-small-en-us-0.15:assets/vosk-model-small-en-us-0.15" \
  scripts/runtime_entry.py
# GUI .app contains the frozen CLI runtime and model data in its resources.
"$B" scripts/generate_icon.py
"$B" -m PyInstaller --noconfirm --clean --windowed --name "WING Voice Assistant" \
  --icon assets/AppIcon.icns --osx-bundle-identifier local.wing.voiceassistant \
  --add-binary "dist/wing-voice-runtime:bin" \
  --add-data "wing_voice:assistant_project/wing_voice" \
  --add-data "config:assistant_project/config" \
  --add-data "assets:assistant_project/assets" \
  --add-data "README.md:assistant_project" \
  --add-data "requirements.txt:assistant_project" \
  --add-data "install.command:assistant_project" \
  --add-data "run.command:assistant_project" \
  --add-data "gui.command:assistant_project" \
  wing_voice/gui.py
# Ensure packaged app has all models even when the editable project is copied on first launch.
RES="dist/WING Voice Assistant.app/Contents/Resources"
mkdir -p "$RES/assistant_project/assets"
cp -R assets/vosk-model-small-en-us-0.15 "$RES/assistant_project/assets/"
cp -R assets/whisper-base.en "$RES/assistant_project/assets/"
# For a universal installer, build each architecture natively and stage the .app.
# Keep staged builds outside build/ because PyInstaller cleans that directory.
if [[ "${BUILD_ARCH_ONLY:-0}" == "1" ]]; then
  if [[ "$ARCH" == "arm64" ]]; then ARCH_NAME="AppleSilicon"; else ARCH_NAME="Intel"; fi
  DEST="universal-build/architectures/$ARCH_NAME"
  mkdir -p "$DEST"
  rm -rf "$DEST/WING Voice Assistant.app"
  ditto "dist/WING Voice Assistant.app" "$DEST/WING Voice Assistant.app"
  printf '%s\n' "$ARCH" > "$DEST/build-architecture.txt"
  echo "Staged $ARCH_NAME app at: $DEST/WING Voice Assistant.app"
  echo "Next, copy this same project folder (including universal-build/) to the other Mac and build there too."
  exit 0
fi
# PKG payload installs app in /Applications. postinstall opens it in the logged-in GUI session.
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/Applications"
cp -R "dist/WING Voice Assistant.app" "$TMP/Applications/"
SCRIPTS="$TMP/scripts"; mkdir -p "$SCRIPTS"
cat > "$SCRIPTS/postinstall" <<'POST'
#!/bin/bash
CONSOLE_USER="$(/usr/bin/stat -f '%Su' /dev/console)"
if [[ -n "$CONSOLE_USER" && "$CONSOLE_USER" != "root" && "$CONSOLE_USER" != "loginwindow" ]]; then
  /bin/launchctl asuser "$(/usr/bin/id -u "$CONSOLE_USER")" /usr/bin/open "/Applications/WING Voice Assistant.app" || true
fi
exit 0
POST
chmod 755 "$SCRIPTS/postinstall"
pkgbuild --root "$TMP" --scripts "$SCRIPTS" --identifier local.wing.voiceassistant --version 1.0.0 --install-location / "dist/WING-Voice-Assistant-All-in-One.pkg"
echo
echo "Built dist/WING-Voice-Assistant-All-in-One.pkg"
echo "Bundled: GUI, frozen Python runtime/dependencies, Vosk wake model, Whisper base.en model."
echo "Not bundled: WING MCP gateway/Node runtime because the gateway path and tool configuration are installation-specific; configure it in the GUI."
echo "No physical WING/Dante hardware validation has been performed. Keep writes disabled until routing and bus mappings are verified."
