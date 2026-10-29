#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Run this on macOS; Apple's pkgbuild tool is required." >&2
  exit 1
fi
BASE="universal-build/architectures"
INTEL="$BASE/Intel/WING Voice Assistant.app"
ARM="$BASE/AppleSilicon/WING Voice Assistant.app"
[[ -d "$INTEL" ]] || { echo "Missing Intel app: $INTEL. Build on an Intel Mac first." >&2; exit 1; }
[[ -d "$ARM" ]] || { echo "Missing Apple Silicon app: $ARM. Build on an Apple Silicon Mac first." >&2; exit 1; }
# Sanity-check that the staging labels match the native build architecture.
[[ "$(cat "$BASE/Intel/build-architecture.txt")" == "x86_64" ]] || { echo "Intel staging marker is not x86_64." >&2; exit 1; }
[[ "$(cat "$BASE/AppleSilicon/build-architecture.txt")" == "arm64" ]] || { echo "Apple Silicon staging marker is not arm64." >&2; exit 1; }
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
ROOT="$WORK/root"
SCRIPTS="$WORK/scripts"
mkdir -p "$ROOT/Library/Application Support/WING Voice Assistant/architectures/Intel" \
         "$ROOT/Library/Application Support/WING Voice Assistant/architectures/AppleSilicon" "$SCRIPTS" dist
ditto "$INTEL" "$ROOT/Library/Application Support/WING Voice Assistant/architectures/Intel/WING Voice Assistant.app"
ditto "$ARM" "$ROOT/Library/Application Support/WING Voice Assistant/architectures/AppleSilicon/WING Voice Assistant.app"
cat > "$SCRIPTS/postinstall" <<'POST'
#!/bin/bash
set -e
BASE="/Library/Application Support/WING Voice Assistant/architectures"
ARCH="$(/usr/bin/uname -m)"
case "$ARCH" in
  arm64) SOURCE="$BASE/AppleSilicon/WING Voice Assistant.app" ;;
  x86_64) SOURCE="$BASE/Intel/WING Voice Assistant.app" ;;
  *) echo "Unsupported Mac architecture: $ARCH" >&2; exit 1 ;;
esac
if [[ ! -d "$SOURCE" ]]; then echo "The installer is missing the app for $ARCH." >&2; exit 1; fi
/usr/bin/install -d -o root -g wheel -m 755 /Applications
/usr/bin/ditto "$SOURCE" "/Applications/WING Voice Assistant.app"
# Keep the selected architecture app in /Applications and remove the staging payload.
/bin/rm -rf "/Library/Application Support/WING Voice Assistant/architectures"
/usr/bin/install -d -o root -g wheel -m 755 "/Library/Application Support/WING Voice Assistant"
CONSOLE_USER="$(/usr/bin/stat -f '%Su' /dev/console 2>/dev/null || true)"
if [[ -n "$CONSOLE_USER" && "$CONSOLE_USER" != "root" && "$CONSOLE_USER" != "loginwindow" ]]; then
  /bin/launchctl asuser "$(/usr/bin/id -u "$CONSOLE_USER")" /usr/bin/open "/Applications/WING Voice Assistant.app" || true
fi
exit 0
POST
chmod 755 "$SCRIPTS/postinstall"
pkgbuild --root "$ROOT" --scripts "$SCRIPTS" \
  --identifier local.wing.voiceassistant.universal --version 1.1.0 \
  --install-location / "dist/WING-Voice-Assistant-Universal.pkg"
echo
echo "Created dist/WING-Voice-Assistant-Universal.pkg"
echo "This installer contains both native app builds and selects one at install time."
echo "This Linux-created archive has not been built or tested on macOS or with WING/Dante hardware."
