"""Small synchronous MCP stdio client for the existing local WING gateway."""
from __future__ import annotations
import json
import os
import select
import subprocess
import time
from pathlib import Path

class MCPError(RuntimeError):
    pass

class StdioMCPClient:
    def __init__(self, gateway_path: str, timeout: float = 15.0):
        self.root = Path(gateway_path).expanduser().resolve()
        self.timeout = timeout
        self.proc = None
        self.next_id = 1
        self.tools = []

    def start(self):
        launcher = self.root / "scripts" / "launcher.mjs"
        if not launcher.is_file():
            raise MCPError(f"Cannot find MCP gateway launcher: {launcher}")
        if not (self.root / "config" / "local.json").is_file():
            raise MCPError(f"Missing {self.root / 'config/local.json'}; configure the existing WING gateway first.")
        self.proc = subprocess.Popen(
            ["node", str(launcher)], cwd=str(self.root), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=None, text=True, bufsize=1,
        )
        self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "wing-voice-assistant", "version": "0.1.0"},
        })
        self._notify("notifications/initialized", {})
        response = self._request("tools/list", {})
        self.tools = response.get("tools", [])
        return self.tools

    def _notify(self, method, params):
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _write(self, payload):
        if not self.proc or self.proc.poll() is not None:
            raise MCPError("MCP gateway process is not running")
        self.proc.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()

    def _request(self, method, params):
        req_id = self.next_id
        self.next_id += 1
        self._write({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.proc.stdout], [], [], max(0.0, deadline-time.monotonic()))
            if not ready:
                break
            line = self.proc.stdout.readline()
            if not line:
                raise MCPError("MCP gateway closed stdout unexpectedly")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") != req_id:
                continue
            if "error" in msg:
                raise MCPError(msg["error"].get("message", str(msg["error"])))
            return msg.get("result", {})
        raise MCPError(f"Timed out waiting for MCP method {method}")

    def call(self, tool_name: str, arguments: dict | None = None):
        if tool_name not in {t.get("name") for t in self.tools}:
            raise MCPError(f"Tool is not exposed by the gateway: {tool_name}")
        return self._request("tools/call", {"name": tool_name, "arguments": arguments or {}})

    def close(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=2)
            except Exception:
                self.proc.terminate()
        self.proc = None
