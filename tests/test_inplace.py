"""Translate-selection draws over the selected text when it can find it on
screen."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from app import inplace, ocr  # noqa: E402

SEL = ("The Architecture and the Elements within the Interior Design need "
       "to show a unique character to elevate the Brand from Design "
       "followers to Design Leaders")
LINES = [
    {"text": "The Architecture and", "box": (105, 190, 290, 36)},
    {"text": "the Elements within", "box": (105, 228, 270, 36)},
    {"text": "the Interior Design", "box": (105, 266, 255, 36)},
    {"text": "need to show a unique", "box": (105, 304, 310, 36)},
    {"text": "character to elevate", "box": (105, 342, 275, 36)},
    {"text": "the Brand from Design", "box": (105, 380, 305, 36)},
    {"text": "followers to Design", "box": (105, 418, 265, 36)},
    {"text": "Leaders", "box": (105, 456, 115, 36)},
    # the next column
    {"text": "Recommended to", "box": (497, 190, 245, 36)},
    {"text": "integrate the elements", "box": (497, 228, 310, 36)},
]


class Find(unittest.TestCase):
    def test_the_selected_block(self):
        box = inplace.find(LINES, SEL)
        self.assertIsNotNone(box)
        x0, y0, x1, y1 = box
        self.assertLess(x1, 497)                 # not the next column
        self.assertLessEqual(y0, 190)
        self.assertGreaterEqual(y1, 456 + 36)

    def test_part_of_a_line(self):
        box = inplace.find(LINES, "unique character to elevate")
        self.assertIsNotNone(box)
        self.assertGreaterEqual(box[1], 290)
        self.assertLessEqual(box[3], 390)

    def test_not_on_screen(self):
        self.assertIsNone(inplace.find(LINES, "Etwas ganz anderes hier"))

    def test_locate_gives_a_snip_area(self):
        img = Image.new("RGB", (1200, 700), "white")
        shot = (img, {"left": 100, "top": 50, "width": 1200,
                      "height": 700}, (250, 350))

        def read(part, source=None):
            return [dict(l) for l in LINES], "en"
        with mock.patch.object(ocr, "image_to_lines", read):
            crop, origin, scale = inplace.locate(SEL, shot)
        self.assertEqual(scale, 1.0)
        self.assertGreater(crop.width, 250)
        self.assertLess(crop.width, 400)
        self.assertGreater(origin[0], 100)


if __name__ == "__main__":
    unittest.main()
