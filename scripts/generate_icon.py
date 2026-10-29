#!/usr/bin/env python3
"""Generate a macOS .icns from the project's SVG icon using Qt's SVG renderer."""
from pathlib import Path
import subprocess
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

root = Path(__file__).resolve().parents[1]
svg = root / "assets" / "AppIcon.svg"
iconset = root / "build" / "AppIcon.iconset"
iconset.mkdir(parents=True, exist_ok=True)
renderer = QSvgRenderer(str(svg))
if not renderer.isValid():
    raise SystemExit(f"Invalid SVG icon: {svg}")

# iconutil accepts these canonical iconset filenames and dimensions.
variants = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}
for filename, size in variants.items():
    image = QImage(QSize(size, size), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    if not image.save(str(iconset / filename)):
        raise SystemExit(f"Could not write {filename}")

out = root / "assets" / "AppIcon.icns"
subprocess.run(["/usr/bin/iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)
print(f"Created {out}")
