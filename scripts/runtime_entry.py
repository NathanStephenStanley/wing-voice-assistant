from pathlib import Path
import sys
# Ensure the project package is visible when PyInstaller analyzes this entrypoint.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wing_voice.cli import main
raise SystemExit(main())
