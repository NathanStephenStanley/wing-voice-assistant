from __future__ import annotations
import argparse
import os
import json
from pathlib import Path
import sys
from .configuration import load_configs, load_json, validate_templates, ConfigError
from .audio import list_devices
from .mcp_client import StdioMCPClient
from .assistant import VoiceAssistant

ROOT = Path(os.environ.get("WING_ASSISTANT_ROOT", Path(__file__).resolve().parents[1])).expanduser().resolve()

def devices():
    for i, d in enumerate(list_devices()):
        if d["max_input_channels"] or d["max_output_channels"]:
            print(f"{i:>2}: {d['name']} | in={d['max_input_channels']} out={d['max_output_channels']} default_sr={d['default_samplerate']}")

def inspect_tools():
    app = load_json(ROOT / "config/app.json")
    gateway = app.get("mcpGatewayPath", "")
    if not gateway or gateway.startswith("/ABSOLUTE/"):
        raise ConfigError("Set mcpGatewayPath in config/app.json first")
    client = StdioMCPClient(gateway)
    try:
        tools = client.start()
        print(json.dumps(tools, indent=2, ensure_ascii=False))
    finally:
        client.close()

def validate():
    problems = validate_templates(ROOT)
    print("Config template check:")
    if problems:
        for p in problems: print(f"- TODO: {p}")
        print("Templates are present; finish the listed setup items before running live audio.")
    else:
        print("- Basic templates look present. This does not validate hardware, tool schemas, or routing.")

def main():
    parser = argparse.ArgumentParser(prog="wing-voice-assistant", description="Local macOS voice assistant for WING Rack")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("devices", help="List CoreAudio devices")
    sub.add_parser("inspect-tools", help="Connect to existing MCP gateway and print actual exposed tools/schemas")
    sub.add_parser("validate", help="Check local config templates")
    sub.add_parser("run", help="Run wake-word and voice assistant")
    args = parser.parse_args()
    try:
        if args.command == "devices": devices(); return 0
        if args.command == "inspect-tools": inspect_tools(); return 0
        if args.command == "validate": validate(); return 0
        app, profiles, tool_map = load_configs(ROOT)
        assistant = VoiceAssistant(ROOT, app, profiles, tool_map)
        assistant.run()
        return 0
    except (ConfigError, RuntimeError, OSError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
