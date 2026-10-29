#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
echo "Building the all-in-one voice-runtime installer. Run this on an Apple Silicon Mac."
exec ./build-all-in-one-pkg.command
