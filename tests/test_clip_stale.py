"""Translate-selection never presents text from before as the selection."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app.main import clip_is_stale
except Exception:                     # pragma: no cover
    clip_is_stale = None


@unittest.skipIf(clip_is_stale is None, "app.main needs the toolkit")
class Stale(unittest.TestCase):
    def test_same_counter_is_stale(self):
        self.assertTrue(clip_is_stale("Im Februar 2026 ...", 41, 41, ""))

    def test_copied_by_hand_since(self):
        self.assertFalse(clip_is_stale("Rund 72 Prozent ...", 42, 41, ""))

    def test_first_use_is_allowed(self):
        self.assertFalse(clip_is_stale("text", 41, None, ""))

    def test_without_a_counter_by_text(self):
        self.assertTrue(clip_is_stale("same text", None, None, "same text"))
        self.assertFalse(clip_is_stale("new text", None, None, "old text"))


if __name__ == "__main__":
    unittest.main()
