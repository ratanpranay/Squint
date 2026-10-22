"""Tables and edges: cells reach into the empty space beside them, words
are never cut in two, glyphs at the edge of a box are covered, unchanged
text is left alone, and ragged German paragraphs stay paragraphs."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402
from app import overlay  # noqa: E402


def table():
    img = Image.new("RGB", (900, 260), "white")
    d = ImageDraw.Draw(img)
    lines = []
    rows = [("施設", "営業時間", "料金"), ("足湯広場", "9:00～17:00", "無料")]
    for r, row in enumerate(rows):
        y = 40 + r * 60
        for c, text in enumerate(row):
            x = 40 + c * 300
            w = 22 * len(text)
            d.rectangle([x, y + 3, x + w, y + 19], fill="black")
            lines.append({"text": text, "box": (x, y, w, 22)})
    return img, lines


class TableTests(unittest.TestCase):
    def test_cell_reaches_right_and_keeps_words_whole(self):
        img, lines = table()
        texts = ["Facility", "Business hours", "Fee", "Foot bath square",
                 "9:00～17:00", "Free"]
        blocks, _ = overlay.layout(img, lines, texts, "en", min_size=10)
        rows = {b["rows"][0]: b for b in blocks}
        self.assertIn("Facility", rows)
        self.assertEqual(rows["Facility"]["rows"], ["Facility"])
        self.assertEqual(len(rows["Business hours"]["rows"]), 1)

    def test_text_that_stays_the_same_is_not_redrawn(self):
        img, lines = table()
        texts = ["Facility", "Business hours", "Fee", "Foot bath square",
                 "9:00～17:00", "Free"]
        blocks, _ = overlay.layout(img, lines, texts, "en", min_size=10)
        self.assertFalse(any("9:00" in " ".join(b["rows"]) for b in blocks))


class EdgeTests(unittest.TestCase):
    def test_glyph_just_outside_the_box_is_taken_in(self):
        img = Image.new("RGB", (400, 60), "white")
        d = ImageDraw.Draw(img)
        d.rectangle([80, 20, 99, 40], fill="black")      # first glyph
        d.rectangle([102, 20, 200, 40], fill="black")    # the rest
        grown = overlay.grow_to_ink(img, (102, 20, 99, 21), (255, 255, 255))
        self.assertLessEqual(grown[0], 80)

    def test_separate_word_is_not_taken_in(self):
        img = Image.new("RGB", (400, 60), "white")
        d = ImageDraw.Draw(img)
        d.rectangle([40, 20, 70, 40], fill="black")      # 30px away
        d.rectangle([102, 20, 200, 40], fill="black")
        grown = overlay.grow_to_ink(img, (102, 20, 99, 21), (255, 255, 255))
        self.assertEqual(grown[0], 102)


class RaggedTests(unittest.TestCase):
    def test_german_paragraph_with_long_words_stays_one(self):
        texts = ["Hiermit kündige ich meine",
                 "Hausratversicherung mit der Vertragsnummer",
                 "HV-2231-778 fristgerecht zum Ende der",
                 "Vertragslaufzeit. Bitte bestätigen Sie mir den",
                 "Vertragsende schriftlich."]
        widths = [245, 426, 360, 410, 225]
        lines = [{"text": t, "box": (100, 100 + i * 30, w, 19)}
                 for i, (t, w) in enumerate(zip(texts, widths))]
        groups = overlay.group_paragraphs(lines)
        self.assertEqual(groups, [[0, 1, 2, 3, 4]])

    def test_two_line_heading_beside_another_column_is_not_two_cells(self):
        lines = [{"text": "Kündigung der", "box": (109, 671, 203, 27)},
                 {"text": "Sicherheitshinweis", "box": (639, 671, 261, 27)},
                 {"text": "Hausratversicherung", "box": (109, 705, 288, 27)}]
        cells = overlay.cells_in(lines)
        self.assertNotIn(0, cells)
        self.assertNotIn(2, cells)


if __name__ == "__main__":
    unittest.main()
