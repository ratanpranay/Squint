"""The time limits every snip is held to, and the pieces a paragraph is
sent to the offline model in."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import budget, offline_model as om, ocr, preread  # noqa: E402


class Line(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(budget.line(400, 800, 2500).endswith("ok"))

    def test_over(self):
        text = budget.line(6011, 6744, 12043)
        self.assertIn("read 6011/800 OVER", text)
        self.assertIn("over: read, first words, done", text)


class Pieces(unittest.TestCase):
    LONG = ("Die Philippinen wurden ursprünglich von Negritos, später von "
            "Austronesiern besiedelt. Seit der Ankunft von Ferdinand "
            "Magellan wurde das Land von Spanien kolonisiert. Seinen Namen "
            "erhielt das Land am 30. September von dem Entdecker z. B. "
            "Dr. Ruy López de Villalobos. In den folgenden mehr als 300 "
            "Jahren setzte sich der Katholizismus durch.")

    def test_short_paragraph_is_one_piece(self):
        self.assertEqual(om._pieces("Ein kurzer Satz. Noch einer."),
                         ["Ein kurzer Satz. Noch einer."])

    def test_long_paragraph_is_whole_sentences(self):
        pieces = om._pieces(self.LONG)
        self.assertGreater(len(pieces), 1)
        self.assertEqual(" ".join(pieces), self.LONG)
        for piece in pieces:
            self.assertLessEqual(len(piece), om.PIECE_CHARS * 1.3)
        self.assertTrue(any("30. September" in p for p in pieces))
        self.assertTrue(any("z. B. Dr. Ruy" in p for p in pieces))

    def test_same_cut_every_time(self):
        self.assertEqual(om._pieces(self.LONG), om._pieces(self.LONG))

    def test_semicolon_but_not_dashes(self):
        long = ("A" * 150 + " – b " + "c" * 150 + "; " + "d" * 120)
        pieces = om._pieces(long)
        self.assertEqual(len(pieces), 2)
        self.assertTrue(pieces[0].endswith(";"))


class BackgroundReading(unittest.TestCase):
    def test_every_background_read_is_quick(self):
        seen = []

        def read(image, source=None):
            seen.append(bool(getattr(ocr._thread, "no_slow", False)))
            return [], "en"
        from PIL import Image
        img = Image.new("RGB", (200, 100), "white")
        reader = preread.Reader()
        with mock.patch.object(ocr, "image_to_lines", read), \
                mock.patch("app.content_area.layers", lambda *a: None):
            for early in (False, True):
                reader._read(img, {"left": 0, "top": 0, "width": 200,
                                   "height": 100}, None, None, early=early)
        self.assertEqual(seen, [True, True])


if __name__ == "__main__":
    unittest.main()
