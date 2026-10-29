import unittest
from wing_voice.actions import resolve_template, extract_value, ActionError

class ActionTests(unittest.TestCase):
    def test_template(self):
        self.assertEqual(resolve_template({"index":"$busIndex","db":"$levelDb"},{"busIndex":4,"levelDb":-12.0}), {"index":4,"db":-12.0})
    def test_explicit_path(self):
        self.assertEqual(extract_value({"structuredContent":{"db":-10.5}}, {"tool":"read","valuePath":"structuredContent.db"}), -10.5)
    def test_no_guessed_path(self):
        with self.assertRaises(ActionError): extract_value({"foo":1},{"tool":"read"})

if __name__ == "__main__": unittest.main()
