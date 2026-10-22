"""Blocks from the page are translated each on its own by the offline
engine, never joined with the next."""
import os, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import offline_model  # noqa: E402


class Whole(unittest.TestCase):
    def test_labels_are_not_joined(self):
        asked = []
        lines = ["传祺M7", "报价 图库 论坛", "奕境X9", "报价 图库 论坛"]
        with mock.patch.object(offline_model, "_ensure_running", lambda: 1), \
                mock.patch.object(offline_model, "translate",
                                  lambda text, target: (asked.append(text),
                                                        "EN")[1]), \
                mock.patch.object(offline_model, "_timing", lambda *a: None):
            out = offline_model.translate_lines(lines, "en", whole=True)
        self.assertEqual(sorted(asked), sorted(lines))
        self.assertEqual(out, ["EN"] * 4)


if __name__ == "__main__":
    unittest.main()
