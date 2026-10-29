import unittest
from wing_voice.intents import parse_intent

class IntentTests(unittest.TestCase):
    def test_relative_fader(self):
        self.assertEqual(parse_intent("turn up Keys 1 by 2 dB"), {"kind":"fader_delta","target":"keys 1","deltaDb":2.0})
        self.assertEqual(parse_intent("turn down Drums by 1.5 dB"), {"kind":"fader_delta","target":"drums","deltaDb":-1.5})
        self.assertEqual(parse_intent("turn up the Keys 1 by one dB"), {"kind":"fader_delta","target":"keys 1","deltaDb":1.0})
    def test_set_fader(self):
        self.assertEqual(parse_intent("set Acoustic to minus 12 dB"), {"kind":"fader_set","target":"acoustic","levelDb":-12.0})
    def test_mute_confirm_cancel_undo(self):
        self.assertEqual(parse_intent("mute Keys 1"), {"kind":"mute","target":"keys 1","muted":True})
        self.assertEqual(parse_intent("unmute Keys 1"), {"kind":"mute","target":"keys 1","muted":False})
        self.assertEqual(parse_intent("confirm"), {"kind":"confirm"})
        self.assertEqual(parse_intent("cancel"), {"kind":"cancel"})
        self.assertEqual(parse_intent("undo"), {"kind":"undo"})
    def test_unknown_rejected(self):
        self.assertIsNone(parse_intent("change the mix however you think sounds good"))

if __name__ == "__main__": unittest.main()
