from __future__ import annotations
import json
import time
from pathlib import Path
import numpy as np
from vosk import Model, KaldiRecognizer, SetLogLevel
from .audio import AudioIO
from .transcription import LocalTranscriber
from .mcp_client import StdioMCPClient, MCPError
from .actions import ActionError, descriptor, call_descriptor, extract_value, path_get
from .intents import parse_intent
from .state import AssistantState

class VoiceAssistant:
    def __init__(self, root: Path, app, profiles, tool_map):
        self.root, self.app, self.profiles, self.tool_map = root, app, profiles, tool_map
        self.audio = AudioIO(app)
        self.mcp = StdioMCPClient(app["mcpGatewayPath"])
        self.state = AssistantState(float(app.get("undoMaxAgeSeconds", 300)))
        self.transcriber = None
        self.wake_model = None
        self.wake_recognizer = None
        self.meter_last_poll = 0.0
        self.meter_flags = set()

    def speak(self, text):
        print(f"ASSISTANT: {text}", flush=True)
        self.audio.drain()
        self.audio.speak(text)
        self.audio.drain()

    def _find_profile(self, target):
        target = " ".join(target.casefold().split())
        for p in self.profiles:
            if " ".join(p["label"].casefold().split()) == target:
                if not isinstance(p.get("busIndex"), int):
                    raise ActionError(f"IEM profile {p['label']} has no verified busIndex. Set it in config/iem-profiles.json.")
                return p
        raise ActionError(f"Unknown IEM profile {target!r}. Use one of: {', '.join(p['label'] for p in self.profiles)}")

    def _read_fader(self, profile):
        d = descriptor(self.tool_map, "busFaderRead")
        r = call_descriptor(self.mcp, self.tool_map, "busFaderRead", {"busIndex": profile["busIndex"]})
        return extract_value(r, d, "number")

    def _read_mute(self, profile):
        d = descriptor(self.tool_map, "busMuteRead")
        r = call_descriptor(self.mcp, self.tool_map, "busMuteRead", {"busIndex": profile["busIndex"]})
        return extract_value(r, d, "bool")

    def _build_write(self, intent):
        if self.app.get("writesEnabled") is not True:
            raise ActionError("Live writes are disabled in config/app.json. Nothing was changed.")
        profile = self._find_profile(intent["target"])
        if intent["kind"] in {"fader_delta", "fader_set"}:
            before = self._read_fader(profile)
            if intent["kind"] == "fader_delta":
                step = float(intent["deltaDb"])
                if abs(step) > float(self.app.get("maxRelativeStepDb", 2.0)):
                    raise ActionError(f"That is larger than the allowed single relative step ({self.app.get('maxRelativeStepDb', 2.0)} dB). Ask for a smaller step.")
                after = before + step
            else:
                after = float(intent["levelDb"])
            if after < -60 or after > float(self.app.get("maxAbsoluteFaderDb", 6.0)):
                raise ActionError(f"Target {after:g} dB is outside the configured safe range (-60 to +{self.app.get('maxAbsoluteFaderDb', 6.0):g} dB).")
            return {"kind":"write", "operation":"fader", "target":profile["label"], "busIndex":profile["busIndex"],
                    "before":before, "after":after, "writeKey":"busFaderSet", "readKey":"busFaderRead",
                    "variablesBefore":{"busIndex":profile["busIndex"], "levelDb":before},
                    "variablesAfter":{"busIndex":profile["busIndex"], "levelDb":after},
                    "readDescriptor":descriptor(self.tool_map,"busFaderRead"), "writeDescriptor":descriptor(self.tool_map,"busFaderSet")}
        if intent["kind"] == "mute":
            before = self._read_mute(profile)
            after = bool(intent["muted"])
            if before == after:
                raise ActionError(f"{profile['label']} is already {'muted' if after else 'unmuted'}.")
            return {"kind":"write", "operation":"mute", "target":profile["label"], "busIndex":profile["busIndex"],
                    "before":before, "after":after, "writeKey":"busMuteSet", "readKey":"busMuteRead",
                    "variablesBefore":{"busIndex":profile["busIndex"], "muted":before},
                    "variablesAfter":{"busIndex":profile["busIndex"], "muted":after},
                    "readDescriptor":descriptor(self.tool_map,"busMuteRead"), "writeDescriptor":descriptor(self.tool_map,"busMuteSet")}
        raise ActionError("Unsupported write intent")

    def _proposal_text(self, action):
        if action["operation"] == "fader":
            return f"{action['target']} bus fader is {action['before']:.1f} dB. Change it to {action['after']:.1f} dB? Say confirm or cancel."
        return f"{action['target']} is currently {'muted' if action['before'] else 'unmuted'}. {'Mute' if action['after'] else 'Unmute'} it? Say confirm or cancel."

    def _read_current_for_action(self, action):
        p = {"label":action["target"], "busIndex":action["busIndex"]}
        return self._read_fader(p) if action["operation"] == "fader" else self._read_mute(p)

    def _execute_pending(self):
        action = self.state.confirmed()
        if not action: return "There is no pending change."
        try:
            # Re-check immediately before the write; the target may have changed while confirmation was pending.
            p = {"label":action["target"], "busIndex":action["busIndex"]}
            current_before_write = self._read_fader(p) if action["operation"] == "fader" else self._read_mute(p)
            if action["operation"] == "fader":
                unchanged = abs(current_before_write - action["before"]) <= 0.25
            else:
                unchanged = current_before_write is action["before"]
            if not unchanged:
                return f"Cancelled for safety: {action['target']} changed while waiting for confirmation. Expected {action['before']!r}, observed {current_before_write!r}. No write sent."
            call_descriptor(self.mcp, self.tool_map, action["writeKey"], action["variablesAfter"])
            # Read-back verification is mandatory; do not journal unverified changes.
            observed = self._read_fader(p) if action["operation"] == "fader" else self._read_mute(p)
            matches = abs(observed - action["after"]) <= 0.25 if action["operation"] == "fader" else observed is action["after"]
            if not matches:
                return f"The write was sent, but read-back verification failed. Expected {action['after']!r}, observed {observed!r}. I will not offer undo because the result is uncertain. Check the console immediately."
            reverse_action = {"operation":action["operation"], "target":action["target"], "busIndex":action["busIndex"],
                              "before":action["after"], "after":action["before"], "writeKey":action["writeKey"],
                              "readKey":action["readKey"], "variablesBefore":action["variablesAfter"],
                              "variablesAfter":action["variablesBefore"], "readDescriptor":action["readDescriptor"],
                              "writeDescriptor":action["writeDescriptor"]}
            self.state.record_verified_change(action["target"], action["before"], action["after"], reverse_action)
            if action["operation"] == "fader": return f"Verified. {action['target']} is now {observed:.1f} dB. Say Wing undo to reverse this change."
            return f"Verified. {action['target']} is now {'muted' if observed else 'unmuted'}. Say Wing undo to reverse this change."
        except Exception as e:
            return f"The change did not complete safely: {e}. Check the mixer before retrying."

    def _propose_undo(self):
        change = self.state.undo_candidate()
        if not change:
            raise ActionError("There is no recent verified change available to undo.")
        action = change["reverseAction"]
        current = self._read_current_for_action(action)
        if action["operation"] == "fader":
            if abs(current - action["before"]) > 0.25:
                raise ActionError(f"Undo refused: {action['target']} changed since the last verified operation (expected {action['before']}, observed {current}).")
            if abs(action["after"] - current) > float(self.app.get("maxRelativeStepDb", 2.0)):
                raise ActionError("Undo would exceed the allowed relative step. No change made; inspect the console and adjust manually.")
        elif current is not action["before"]:
            raise ActionError("Undo refused because the mute state no longer matches the last verified change.")
        self.state.propose(action)
        return self._proposal_text(action)

    def _handle_intent(self, text):
        # Wake word may be included in the transcript; strip it before parsing.
        normalized = text.strip()
        normalized = __import__('re').sub(r"^(?:hey\s+)?wing[,.\s]+", "", normalized, flags=__import__('re').I).strip()
        intent = parse_intent(normalized)
        if not intent:
            self.speak("I didn't understand that command. No action taken.")
            return
        try:
            if intent["kind"] == "confirm":
                if not self.state.pending:
                    self.speak("There is no pending change to confirm.")
                else:
                    self.speak(self._execute_pending())
                return
            if intent["kind"] == "cancel":
                self.state.cancel(); self.speak("Cancelled. No change made."); return
            if intent["kind"] == "undo":
                self.speak(self._propose_undo())
                self._confirmation_window()
                return
            if intent["kind"] == "status":
                if self.tool_map.get("statusRead"):
                    result = call_descriptor(self.mcp, self.tool_map, "statusRead", {})
                    self.speak("Status read completed. Check the assistant log for the returned details.")
                    print(json.dumps(result, indent=2, default=str))
                elif self.tool_map.get("meterRead"):
                    result = call_descriptor(self.mcp, self.tool_map, "meterRead", {})
                    self.speak("Meter read completed. Check the assistant log for the returned details.")
                    print(json.dumps(result, indent=2, default=str))
                else:
                    self.speak("Status reading is not configured yet. No change made.")
                return
            action = self._build_write(intent)
            self.state.propose(action)
            self.speak(self._proposal_text(action))
            self._confirmation_window()
        except (ActionError, MCPError, KeyError, ValueError) as e:
            self.speak(f"I can't safely do that: {e}. No further action taken.")

    def _confirmation_window(self):
        self.audio.drain()
        timeout = float(self.app.get("confirmationTimeoutSeconds", 12))
        deadline = time.monotonic() + timeout
        # Wake detection is disabled in this state. Only a single confirm/cancel utterance is accepted.
        while time.monotonic() < deadline and self.state.pending:
            utterance = self.audio.record_utterance(max_seconds=min(5, timeout), silence_end_seconds=0.7, start_timeout=1.5)
            if utterance is None: continue
            self.audio.drain()
            text = self.transcriber.transcribe(utterance, self.audio.in_rate)
            print(f"CONFIRMATION HEARD: {text!r}", flush=True)
            normalized = __import__('re').sub(r"^(?:hey\s+)?wing[,.\s]+", "", text.strip(), flags=__import__('re').I).strip()
            intent = parse_intent(normalized)
            if intent and intent["kind"] == "confirm":
                self.speak(self._execute_pending()); return
            if intent and intent["kind"] == "cancel":
                self.state.cancel(); self.speak("Cancelled. No change made."); return
            self.speak("Please say confirm or cancel. No change has been made yet.")
            self.audio.drain()
        if self.state.pending:
            self.state.cancel()
            self.speak("Confirmation timed out. Cancelled; no change made.")

    def _meter_poll(self):
        if not self.app.get("meterMonitoringEnabled") or not self.tool_map.get("meterRead"):
            return False
        now = time.monotonic()
        if now - self.meter_last_poll < float(self.app.get("meterPollSeconds", 2.0)):
            return False
        self.meter_last_poll = now
        try:
            result = call_descriptor(self.mcp, self.tool_map, "meterRead", {})
            d = descriptor(self.tool_map, "meterRead")
            values = extract_value(result, d, "raw")
            if isinstance(values, (int, float)): values = [float(values)]
            if not isinstance(values, list): return False
            vals = [float(v) for v in values if isinstance(v, (int, float))]
            if not vals: return False
            thresholds = self.app.get("meterThresholdsDbfs", {})
            conditions = set()
            if max(vals) >= float(thresholds.get("clipAtOrAbove", -1.0)): conditions.add("clip")
            if max(vals) <= float(thresholds.get("noSignalAtOrBelow", -60.0)): conditions.add("no-signal")
            if conditions != self.meter_flags:
                self.meter_flags = conditions
                if conditions:
                    msg = "Meter alert: " + ("possible clipping. " if "clip" in conditions else "") + ("signal appears absent. " if "no-signal" in conditions else "") + "I have not changed any mixer settings."
                    self.speak(msg)
                    return True
            return False
        except Exception as e:
            print(f"Meter monitor disabled for this poll: {e}", flush=True)
            return False

    def run(self):
        tools = self.mcp.start()
        print("Exposed MCP tools:", ", ".join(t.get("name", "?") for t in tools), flush=True)
        self.audio.start()
        whisper_model = Path(self.app.get("whisperModel", "base.en"))
        if not whisper_model.is_absolute() and (self.root / whisper_model).exists():
            whisper_model = self.root / whisper_model
        self.transcriber = LocalTranscriber(str(whisper_model))
        SetLogLevel(-1)
        model_path = Path(self.app.get("wakeModelPath", str(self.root / "assets" / "vosk-model-small-en-us-0.15")))
        if not model_path.is_absolute(): model_path = self.root / model_path
        if not (model_path / "am" / "final.mdl").exists():
            raise RuntimeError(f"Open-source wake model not found at {model_path}. Reinstall the bundled model or set wakeModelPath.")
        self.wake_model = Model(str(model_path))
        self.wake_recognizer = KaldiRecognizer(self.wake_model, 16000, '["wing", "Wing", "[unk]"]')
        print("Ready. Say 'Wing' to activate. Press Ctrl+C to exit.", flush=True)
        self.speak("WING assistant ready.")
        resample_buffer = np.empty(0, dtype=np.float32)
        try:
            while True:
                chunk = self.audio.get_chunk(timeout=0.1)
                if self._meter_poll():
                    resample_buffer = np.empty(0, dtype=np.float32)
                    self.audio.drain()
                    continue
                if chunk is None: continue
                if self.state.busy or self.state.pending:
                    # Explicitly discard while speaking/confirming; never queue a wake or command.
                    resample_buffer = np.empty(0, dtype=np.float32)
                    continue
                if self.audio.in_rate != 16000:
                    from scipy.signal import resample_poly
                    from math import gcd
                    g = gcd(self.audio.in_rate, 16000)
                    converted = resample_poly(chunk, 16000 // g, self.audio.in_rate // g)
                else: converted = chunk
                pcm = np.clip(converted * 32767.0, -32768, 32767).astype(np.int16)
                detected = self.wake_recognizer.AcceptWaveform(pcm.tobytes())
                # Vosk grammar is constrained to the wake word and unknown speech.
                if detected:
                    try: result = json.loads(self.wake_recognizer.Result())
                    except Exception: result = {}
                    heard = str(result.get("text", "")).strip().casefold().split()
                    if "wing" in heard:
                        resample_buffer = np.empty(0, dtype=np.float32)
                        self.audio.drain()
                        self.speak("Yes?")
                        utterance = self.audio.record_utterance(
                            max_seconds=float(self.app.get("recordingMaxSeconds", 8)),
                            silence_end_seconds=float(self.app.get("silenceEndSeconds", 1.0)),
                            start_timeout=4.0)
                        self.audio.drain()
                        if utterance is None:
                            self.speak("I didn't hear a command. No action taken.")
                        else:
                            text = self.transcriber.transcribe(utterance, self.audio.in_rate)
                            print(f"HEARD: {text!r}", flush=True)
                            self._handle_intent(text)
                        self.wake_recognizer.Reset()
                        resample_buffer = np.empty(0, dtype=np.float32)
                    else:
                        self.wake_recognizer.Reset()
        except KeyboardInterrupt:
            print("Stopping voice assistant…", flush=True)
        finally:
            self.audio.close(); self.mcp.close()
