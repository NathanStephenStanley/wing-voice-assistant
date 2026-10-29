from __future__ import annotations
import math
import os
import queue
import subprocess
import tempfile
import time
from pathlib import Path
import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly
from scipy.io import wavfile
from math import gcd

class AudioSetupError(RuntimeError):
    pass

def list_devices():
    return sd.query_devices()

def find_device(fragment: str, kind: str):
    devices = sd.query_devices()
    need = "max_input_channels" if kind == "input" else "max_output_channels"
    matches = [(i, d) for i, d in enumerate(devices) if fragment.casefold() in d["name"].casefold() and d[need] > 0]
    if not matches:
        raise AudioSetupError(f"No {kind} device with {fragment!r} in its name. Run the devices command and update config/app.json.")
    if len(matches) > 1:
        names = "; ".join(f"{i}: {d['name']}" for i, d in matches)
        raise AudioSetupError(f"Device match is ambiguous ({names}); use a more specific name fragment.")
    return matches[0]

class AudioIO:
    def __init__(self, app_config):
        self.cfg = app_config
        self.q = queue.Queue(maxsize=120)
        self.input_index, self.input_info = find_device(app_config["inputDeviceContains"], "input")
        self.output_index, self.output_info = find_device(app_config["outputDeviceContains"], "output")
        self.in_channels = [int(x) for x in app_config.get("inputChannels", [0])]
        self.out_channels = [int(x) for x in app_config.get("outputChannels", [0])]
        if not self.in_channels or min(self.in_channels) < 0 or max(self.in_channels) >= self.input_info["max_input_channels"]:
            raise AudioSetupError(f"inputChannels {self.in_channels} exceed device input count {self.input_info['max_input_channels']}")
        if not self.out_channels or min(self.out_channels) < 0 or max(self.out_channels) >= self.output_info["max_output_channels"]:
            raise AudioSetupError(f"outputChannels {self.out_channels} exceed device output count {self.output_info['max_output_channels']}")
        self.in_rate = int(app_config.get("inputSampleRate", 48000))
        self.out_rate = int(app_config.get("outputSampleRate", 48000))
        self.stream = None

    def start(self):
        nchan = max(self.in_channels) + 1
        def callback(indata, frames, time_info, status):
            if status:
                # Drop diagnostics to stderr only; never emit from audio callback.
                pass
            mono = np.mean(indata[:, self.in_channels], axis=1).astype(np.float32)
            try:
                self.q.put_nowait(mono.copy())
            except queue.Full:
                try: self.q.get_nowait()
                except queue.Empty: pass
                try: self.q.put_nowait(mono.copy())
                except queue.Full: pass
        self.stream = sd.InputStream(device=self.input_index, samplerate=self.in_rate,
                                     channels=nchan, dtype="float32", blocksize=1024,
                                     callback=callback)
        self.stream.start()

    def close(self):
        if self.stream:
            self.stream.stop(); self.stream.close(); self.stream = None

    def drain(self):
        while True:
            try: self.q.get_nowait()
            except queue.Empty: break

    def get_chunk(self, timeout=0.5):
        try: return self.q.get(timeout=timeout)
        except queue.Empty: return None

    def record_utterance(self, max_seconds=8, silence_end_seconds=1.0, start_timeout=5.0):
        chunks = []
        started = False
        last_voice = None
        start = time.monotonic()
        end_deadline = start + start_timeout
        sample_count = 0
        # Adaptive silence floor with conservative minimum; speech is expected at talkback level.
        threshold = float(self.cfg.get("speechRmsThreshold", 0.008))
        while time.monotonic() - start < max_seconds:
            chunk = self.get_chunk(timeout=0.2)
            now = time.monotonic()
            if chunk is None:
                if not started and now > end_deadline: return None
                if started and last_voice and now - last_voice >= silence_end_seconds: break
                continue
            rms = float(np.sqrt(np.mean(np.square(chunk))) + 1e-12)
            if rms >= threshold:
                started = True; last_voice = now
            elif started and last_voice is None:
                last_voice = now
            if started:
                chunks.append(chunk); sample_count += len(chunk)
                if last_voice is None: last_voice = now
                if now - last_voice >= silence_end_seconds: break
        if not chunks:
            return None
        return np.concatenate(chunks)

    def play_file(self, path: Path):
        rate, data = wavfile.read(str(path))
        if data.ndim > 1: data = data.mean(axis=1)
        if np.issubdtype(data.dtype, np.integer):
            data = data.astype(np.float32) / max(abs(np.iinfo(data.dtype).min), np.iinfo(data.dtype).max)
        else: data = data.astype(np.float32)
        target_rate = self.out_rate
        if rate != target_rate:
            g = gcd(int(rate), int(target_rate))
            data = resample_poly(data, target_rate // g, int(rate) // g).astype(np.float32)
            rate = target_rate
        nout = max(self.out_channels) + 1
        out = np.zeros((len(data), nout), dtype=np.float32)
        for ch in self.out_channels: out[:, ch] = data
        sd.play(out, samplerate=rate, device=self.output_index, blocking=True)

    def speak(self, text: str):
        # Use the built-in macOS TTS engine and route generated audio to the selected DVS output.
        with tempfile.TemporaryDirectory(prefix="wing-voice-") as td:
            aiff = Path(td) / "speech.aiff"
            wav = Path(td) / "speech.wav"
            subprocess.run(["say", "-o", str(aiff), text], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@22050", str(aiff), str(wav)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            self.play_file(wav)
