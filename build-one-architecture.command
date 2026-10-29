#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Run this on a real Mac; native macOS dependencies cannot be built on Linux." >&2
  exit 1
fi
ARCH="$(uname -m)"
case "$ARCH" in
  arm64) LABEL="Apple Silicon (arm64)" ;;
  x86_64) LABEL="Intel (x86_64)" ;;
  *) echo "Unsupported Mac architecture: $ARCH" >&2; exit 1 ;;
esac
echo "Building the $LABEL version. This may take a while and downloads speech models."
BUILD_ARCH_ONLY=1 ./build-all-in-one-pkg.command
