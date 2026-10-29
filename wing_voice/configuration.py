from __future__ import annotations
import json
from pathlib import Path

class ConfigError(ValueError):
    pass

def load_json(path: Path, required=True):
    if not path.exists():
        if required:
            raise ConfigError(f"Missing config file: {path}")
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as e:
        raise ConfigError(f"Invalid JSON in {path}: {e}") from e

def load_configs(root: Path):
    app = load_json(root / "config/app.json")
    profiles = load_json(root / "config/iem-profiles.json").get("profiles", [])
    tool_map = load_json(root / "config/tool-map.json")
    wake_path = Path(app.get("wakeModelPath", "assets/vosk-model-small-en-us-0.15"))
    if not wake_path.is_absolute(): wake_path = (root / wake_path).resolve()
    if not (wake_path / "am" / "final.mdl").exists():
        raise ConfigError(f"Missing open-source Vosk wake model folder: {wake_path}")
    app["wakeModelPath"] = str(wake_path)
    if not app.get("mcpGatewayPath") or app["mcpGatewayPath"].startswith("/ABSOLUTE/"):
        raise ConfigError("Set mcpGatewayPath in config/app.json")
    if len(profiles) != 6:
        raise ConfigError("iem-profiles.json must contain exactly six profiles")
    labels = [str(p.get("label", "")).casefold() for p in profiles]
    if any(not x for x in labels) or len(set(labels)) != 6:
        raise ConfigError("IEM profile labels must be non-empty and unique")
    return app, profiles, tool_map

def validate_templates(root: Path):
    # Lightweight validation deliberately does not require audio devices or secrets.
    app = load_json(root / "config/app.json", required=False)
    profiles = load_json(root / "config/iem-profiles.json", required=False).get("profiles", [])
    tool_map = load_json(root / "config/tool-map.json", required=False)
    problems = []
    if app.get("writesEnabled") is not False:
        problems.append("writesEnabled should remain false during setup")
    if len(profiles) != 6:
        problems.append("configure exactly six IEM profiles")
    if not tool_map:
        problems.append("configure tool-map.json after inspecting live MCP tools")
    return problems
