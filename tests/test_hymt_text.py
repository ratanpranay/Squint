"""Copied text of many lines goes through the offline engine sentence by
sentence, not all at once (which failed on a line-count mismatch)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import offline_model, translator  # noqa: E402


class HymtText(unittest.TestCase):
    def test_many_lines_use_translate_lines(self):
        with mock.patch.object(offline_model, "translate_lines",
                               lambda lines, target: ["EN " + l if l.strip()
                                                      else "" for l in lines]), \
                mock.patch.object(offline_model, "translate",
                                  side_effect=AssertionError("whole text")):
            out = translator._hymt("第一行\n\n第二行", "zh", "en")
        self.assertEqual(out, "EN 第一行\n\nEN 第二行")

    def test_one_line_is_translated_directly(self):
        with mock.patch.object(offline_model, "translate",
                               lambda text, target: "EN " + text):
            self.assertEqual(translator._hymt("你好", "zh", "en"), "EN 你好")


if __name__ == "__main__":
    unittest.main()
