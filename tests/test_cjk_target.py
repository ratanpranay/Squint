"""Translating into Chinese or Japanese: a paragraph's translation covers
all of its lines, not just the first."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402

from app import offline_model, overlay  # noqa: E402


class Share(unittest.TestCase):
    L = [{"box": (0, 0, 600, 30)}, {"box": (0, 40, 600, 30)},
         {"box": (0, 80, 300, 30)}]

    def test_chinese_by_characters(self):
        parts = overlay.split_over(self.L, [0, 1, 2],
                                   u"里昂是法国东南部的一个市镇，位于罗讷河与索恩河的汇合处。")
        self.assertTrue(all(parts[i] for i in (0, 1, 2)))
        self.assertEqual("".join(parts[i] for i in (0, 1, 2)),
                         u"里昂是法国东南部的一个市镇，位于罗讷河与索恩河的汇合处。")

    def test_english_by_words(self):
        parts = overlay.split_over(self.L, [0, 1, 2],
                                   "Lyon is a commune in south-east France.")
        self.assertEqual(" ".join(parts[i] for i in (0, 1, 2)),
                         "Lyon is a commune in south-east France.")


class Covered(unittest.TestCase):
    def test_every_line_of_a_short_translation_is_covered(self):
        img = Image.new("RGB", (800, 200), "white")
        d = ImageDraw.Draw(img)
        lines = []
        for i in range(4):
            d.rectangle((20, 20 + 40 * i, 700, 40 + 40 * i), fill="black")
            lines.append({"text": "Lyon est une commune du sud-est %d" % i,
                          "box": (20, 20 + 40 * i, 680, 20), "para": 0,
                          "para_text": u"里昂是法国东南部的一个市镇。"})
        texts = [u"里昂是法国东南部的一个市镇。", "", "", ""]
        blocks, _tall = overlay.layout(img, lines, texts, "zh-CN")
        covered = [b["cover"] for b in blocks]
        bottom = max(c[3] for c in covered)
        self.assertGreaterEqual(bottom, 20 + 40 * 3 + 20 - 2)


class Labels(unittest.TestCase):
    def test_short_items_are_asked_as_labels(self):
        from unittest import mock
        asked = []
        with mock.patch.object(offline_model, "_ask",
                               lambda content, budget: (asked.append(
                                   content) or "Home")), \
                mock.patch.object(offline_model, "_ensure_running",
                                  lambda: 1):
            out = offline_model.translate_lines(["Accueil"], "en",
                                                whole=True)
        self.assertEqual(out, ["Home"])
        self.assertIn(offline_model.LABEL_CONTEXT, asked[0])

    def test_label_context_leak_falls_back(self):
        calls = []

        def ask(content, budget):
            calls.append(content)
            return u"按钮：主页" if len(calls) == 1 else "Home"
        saved = offline_model._ask
        try:
            offline_model._ask = ask
            self.assertEqual(offline_model.translate_label("Accueil", "en"),
                             "Home")
        finally:
            offline_model._ask = saved


if __name__ == "__main__":
    unittest.main()
