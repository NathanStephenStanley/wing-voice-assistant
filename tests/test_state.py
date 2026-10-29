import unittest
from wing_voice.state import AssistantState

class StateTests(unittest.TestCase):
    def test_single_pending_and_cancel(self):
        s=AssistantState(); s.propose({"id":1})
        with self.assertRaises(RuntimeError): s.propose({"id":2})
        s.cancel(); self.assertIsNone(s.pending)
    def test_confirm_returns_pending(self):
        s=AssistantState(); x={"id":1}; s.propose(x)
        self.assertEqual(s.confirmed(), x); self.assertIsNone(s.pending)
    def test_undo_needs_reverse_action(self):
        s=AssistantState(); s.record_verified_change("Keys 1", -12, -11, None)
        self.assertIsNone(s.undo_candidate())
        s.record_verified_change("Keys 1", -12, -11, {"after":-12})
        self.assertEqual(s.undo_candidate()["target"], "Keys 1")

if __name__ == "__main__": unittest.main()
