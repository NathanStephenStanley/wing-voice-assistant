from __future__ import annotations
import numpy as np
from scipy.signal import resample_poly
from math import gcd

class LocalTranscriber:
    def __init__(self, model_name="base.en"):
        from faster_whisper import WhisperModel
        self.model = WhisperModel(model_name, device="cpu", compute_type="int8")

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        if audio is None or len(audio) == 0:
            return ""
        x = audio.astype(np.float32)
        if sample_rate != 16000:
            g = gcd(int(sample_rate), 16000)
            x = resample_poly(x, 16000 // g, int(sample_rate) // g).astype(np.float32)
        segments, _ = self.model.transcribe(x, language="en", beam_size=3, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()
