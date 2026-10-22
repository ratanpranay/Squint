"""Run check: three test pages through the snip's path, judged."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import selfcheck


class FakeTranslator:
    def __init__(self, keep=()):
        self.keep = keep

    def translate_lines(self, lines, target="en", source="auto", job=None,
                        blocks=True, **_kw):
        return [l if any(k in l for k in self.keep) else
                "This is the translation of item %d here." % i
                for i, l in enumerate(lines)]


def read_exactly(lines):
    out, y = [], 24
    for text in lines:
        if text:
            out.append({"text": text, "box": (24, y, 9 * len(text), 18)})
        y += 24
    return out


class Check(unittest.TestCase):
    def run_page(self, keep=(), slow=0.0):
        title, lines = selfcheck.PAGES_DE[1]
        clock = {"t": 0.0}

        def fake_read(img, lang=None, psm=6, source=None):
            clock["t"] += 0.2
            return read_exactly(lines), "fake"
        with mock.patch("app.ocr.image_to_lines", fake_read), \
                mock.patch("app.selfcheck.time.monotonic",
                           side_effect=lambda: clock["t"]), \
                mock.patch("app.overlay.progressive",
                           side_effect=self.progressive(keep, slow, clock)):
            return selfcheck.check_page(title, lines, "de", "en",
                                        FakeTranslator(keep))

    def progressive(self, keep, slow, clock):
        from app import overlay

        def run(image, lines, translator, target, source, floor, **kw):
            clock["t"] += slow
            texts = overlay.translate_grouped(lines, translator, target)
            blocks, tall = overlay.layout(image, lines, texts, target,
                                          min_size=floor)
            return texts, blocks, tall
        return run

    def test_good_page_passes(self):
        result = self.run_page()
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["read"][0], result["read"][1])

    def test_paragraph_left_in_german_fails(self):
        result = self.run_page(keep=("Verbraucherschützer",))
        self.assertTrue(any("left untranslated" in p
                            for p in result["problems"]))

    def test_slow_page_fails(self):
        result = self.run_page(slow=3.5)
        self.assertTrue(any(p.startswith("took") for p in result["problems"]))

    def test_pages_are_drawn(self):
        image = selfcheck.draw_page(selfcheck.PAGES_DE[0][1], 1.0)
        self.assertGreater(image.height, 200)
        self.assertEqual(selfcheck._pages("de")[1], "en")
        self.assertEqual(selfcheck._pages("en")[1], "de")


if __name__ == "__main__":
    unittest.main()
