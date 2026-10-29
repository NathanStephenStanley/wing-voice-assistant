"""Conservative, deterministic voice intent parser. Unknown wording is rejected."""
from __future__ import annotations
import re

NUM = r"(?:(?:minus\s+)?(?:\d+(?:\.\d+)?|zero|one|two|three|four|five|six|seven|eight|nine|ten|half))"

def _number(s: str) -> float:
    text = s.strip().casefold()
    negative = text.startswith("minus ")
    text = text.removeprefix("minus ").strip()
    words = {"zero":0, "one":1, "two":2, "three":3, "four":4, "five":5, "six":6, "seven":7, "eight":8, "nine":9, "ten":10, "half":0.5}
    if text in words: v = float(words[text])
    else: v = float(re.search(r"\d+(?:\.\d+)?", text).group(0))
    return -v if negative else v

def parse_intent(text: str):
    raw = text.strip()
    s = re.sub(r"[^\w.\-\s]", " ", raw.casefold())
    s = re.sub(r"\s+", " ", s).strip()
    if s in {"confirm", "yes confirm", "do it", "go ahead"}:
        return {"kind": "confirm"}
    if s in {"cancel", "no", "never mind", "nevermind", "stop"}:
        return {"kind": "cancel"}
    if s in {"undo", "undo that", "reverse that", "revert that"}:
        return {"kind": "undo"}
    if s in {"status", "mixer status", "what is the status", "meters", "check meters"}:
        return {"kind": "status"}
    m = re.fullmatch(rf"(?:turn|bring)\s+(up|down)\s+(.+?)\s+by\s+({NUM})(?:\s+db)?", s)
    if m:
        amount = _number(m.group(3))
        if amount < 0: return None
        target = re.sub(r"^the\s+", "", m.group(2).strip())
        return {"kind": "fader_delta", "target": target, "deltaDb": amount * (1 if m.group(1) == "up" else -1)}
    m = re.fullmatch(rf"set\s+(.+?)\s+(?:to\s+)?({NUM})\s*(?:db)?", s)
    if m:
        target = re.sub(r"^the\s+", "", m.group(1).strip())
        return {"kind": "fader_set", "target": target, "levelDb": _number(m.group(2))}
    m = re.fullmatch(r"(mute|unmute)\s+(.+)", s)
    if m:
        target = re.sub(r"^the\s+", "", m.group(2).strip())
        return {"kind": "mute", "target": target, "muted": m.group(1) == "mute"}
    return None
