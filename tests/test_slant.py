"""Text written at an angle is translated label by label and drawn back
at its own angle."""
import math
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont

from app import overlay, slant, watermark

try:
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
except Exception:                     # pragma: no cover
    root = None


def diagonal(cx, cy, length, thick, degrees):
    """Four corners of a line `length` long at `degrees` (screen, y down),
    in the order PaddleOCR gives them: clockwise from the top left."""
    a = math.radians(degrees)
    ux, uy = math.cos(a), math.sin(a)
    nx, ny = -uy, ux
    sx = cx - ux * length / 2 - nx * thick / 2
    sy = cy - uy * length / 2 - ny * thick / 2
    return [(sx, sy), (sx + ux * length, sy + uy * length),
            (sx + ux * length + nx * thick, sy + uy * length + ny * thick),
            (sx + nx * thick, sy + ny * thick)]


def line_for(text, points):
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    line = {"text": text, "box": (int(min(xs)), int(min(ys)),
                                  int(max(xs) - min(xs)),
                                  int(max(ys) - min(ys)))}
    return slant.attach(line, points)


class Corners(unittest.TestCase):
    def test_level_text_is_left_alone(self):
        line = line_for("Level heading", diagonal(200, 100, 300, 30, 2))
        self.assertNotIn("quad", line)

    def test_up_to_the_right(self):
        line = line_for("Komfort Heck, N/mm", diagonal(300, 300, 400, 40,
                                                       -45))
        self.assertTrue(slant.is_slanted(line))
        self.assertAlmostEqual(line["angle"], -45, delta=1)
        length, thick = slant.size_of(slant.corners(line))
        self.assertAlmostEqual(length, 400, delta=4)
        self.assertAlmostEqual(thick, 40, delta=4)

    def test_order_of_corners_does_not_matter(self):
        pts = diagonal(300, 300, 400, 40, -45)
        turned = pts[1:] + pts[:1]
        line = line_for("Komfort Heck, N/mm", turned)
        self.assertAlmostEqual(line["angle"], -45, delta=1)

    def test_steep_line_reads_downward(self):
        line = line_for("V Der Findling", diagonal(300, 300, 160, 30, 75))
        self.assertAlmostEqual(line["angle"], 75, delta=1)

    def test_digits_and_squares_have_no_direction(self):
        self.assertNotIn("quad", line_for("5", diagonal(50, 50, 30, 28, 90)))
        self.assertNotIn("quad", line_for("1,0", diagonal(50, 50, 30, 28,
                                                          -6)))

    def test_upright_cjk_column_is_not_turned(self):
        self.assertNotIn("quad", line_for(u"日本語の縦書き",
                                          diagonal(50, 200, 300, 40, 90)))

    def test_vision_keeps_its_direction(self):
        pts = diagonal(300, 300, 400, 40, 160)
        line = {"text": "upside", "box": (0, 0, 1, 1)}
        slant.attach(line, pts, ordered=True)
        self.assertAlmostEqual(line["angle"], 160, delta=1)

    def test_corners_follow_the_box(self):
        line = line_for("Komfort Heck, N/mm", diagonal(300, 300, 400, 40,
                                                       -45))
        big = overlay.scale_lines([line], 2.0)[0]
        length, thick = slant.size_of(slant.corners(big))
        self.assertAlmostEqual(length, 800, delta=10)
        self.assertAlmostEqual(thick, 80, delta=4)


def page_with_labels():
    """A white page with diagonal labels drawn on it, and their lines."""
    image = Image.new("RGB", (900, 500), "white")
    words = ["Gewicht Komplettrad", "Komfort Heck", "Komfort Front",
             "Schaltung", "Bremsen"]
    lines = []
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
    for i, word in enumerate(words):
        row = Image.new("RGBA", (420, 40), (0, 0, 0, 0))
        ImageDraw.Draw(row).text((4, 4), word, font=font, fill=(20, 20, 20))
        turned = row.rotate(45, expand=True)
        x, y = 40 + i * 150, 60
        image.paste(turned, (x, y), turned)
        cx, cy = x + turned.width / 2.0, y + turned.height / 2.0
        lines.append(line_for(word, diagonal(cx, cy, 420, 40, -45)))
    return image, lines


class Translate:
    def __init__(self):
        self.sent = []

    def translate_lines(self, sent, target="en", source="auto", job=None,
                        blocks=True):
        self.sent.append(list(sent))
        return ["[%s]" % s for s in sent]


class Page(unittest.TestCase):
    def test_each_label_is_translated_on_its_own(self):
        image, lines = page_with_labels()
        engine = Translate()
        overlay.translate_grouped(lines, engine, "en")
        self.assertEqual(len(engine.sent[0]), len(lines))
        self.assertIn("Komfort Heck", engine.sent[0])

    def test_labels_are_drawn_at_their_angle(self):
        image, lines = page_with_labels()
        texts = overlay.translate_grouped(lines, Translate(), "en")
        blocks, _tall = overlay.layout(image, lines, texts, "en")
        turned = [b for b in blocks if b.get("turned")]
        self.assertEqual(len(turned), len(lines))
        self.assertEqual(overlay.lines_covered(blocks), len(lines))
        shape, middle, angle, text = overlay.turned_parts(turned[0])
        self.assertAlmostEqual(angle, 45, delta=1)    # Tk: anticlockwise
        self.assertTrue(text.startswith("["))
        self.assertEqual(len(shape), 4)
        # White paper, dark ink.
        self.assertGreater(sum(turned[0]["bg"]), 600)
        self.assertLess(sum(turned[0]["fg"]), 300)
        painted = overlay.paint(image, blocks)
        self.assertEqual(painted.size, image.size)

    def test_moving_a_block_moves_its_shape(self):
        image, lines = page_with_labels()
        texts = overlay.translate_grouped(lines, Translate(), "en")
        blocks, _tall = overlay.layout(image, lines, texts, "en")
        block = [b for b in blocks if b.get("turned")][0]
        moved = dict(block)
        x0, y0, x1, y1 = block["cover"]
        moved["cover"] = (x0 + 100, y0 + 50, x1 + 100, y1 + 50)
        a = overlay.turned_parts(block)
        b = overlay.turned_parts(moved)
        self.assertAlmostEqual(b[1][0] - a[1][0], 100)
        self.assertAlmostEqual(b[1][1] - a[1][1], 50)

    def test_long_translation_stays_inside(self):
        image, lines = page_with_labels()
        texts = ["A much much longer translation of this label " * 2] * \
            len(lines)
        for i, line in enumerate(lines):
            line["para"], line["para_text"] = i, texts[i]
        blocks, _tall = overlay.layout(image, lines, texts, "en")
        for block in blocks:
            shape = overlay.turned_parts(block)[0]
            self.assertGreaterEqual(min(y for _x, y in shape), -40)


class Watermarks(unittest.TestCase):
    def test_big_slanted_title_is_kept(self):
        self.assertFalse(watermark.looks_like_watermark(
            ["tilted 16 degrees", "4.1x the size of the page"]))

    def test_pale_slanted_mark_still_goes(self):
        self.assertTrue(watermark.looks_like_watermark(
            ["tilted 30 degrees", "faint (contrast 40)"]))
        self.assertTrue(watermark.looks_like_watermark(
            ["repeated 4 times", "3.0x the size of the page"]))

    def test_height_of_a_slanted_line_is_its_thickness(self):
        line = line_for("Komfort Heck, N/mm", diagonal(300, 300, 400, 40,
                                                       -45))
        self.assertAlmostEqual(watermark._height(line), 40, delta=4)


@unittest.skipIf(root is None, "no display")
class Screen(unittest.TestCase):
    def test_overlay_draws_turned_text(self):
        from app import ui_result
        image, lines = page_with_labels()
        texts = overlay.translate_grouped(lines, Translate(), "en")
        blocks, _tall = overlay.layout(image, lines, texts, "en")
        canvas = tk.Canvas(root, width=900, height=500)
        fake = types.SimpleNamespace(canvas=canvas, _shrink=1.0,
                                     _hex=ui_result.OverlayWindow._hex)
        ui_result.OverlayWindow._paint_blocks(fake, blocks)
        texts_drawn = [i for i in canvas.find_all()
                       if canvas.type(i) == "text"]
        self.assertEqual(len(texts_drawn), len(lines))
        self.assertAlmostEqual(float(canvas.itemcget(texts_drawn[0],
                                                     "angle")), 45, delta=1)
        polygons = [i for i in canvas.find_all()
                    if canvas.type(i) == "polygon"]
        self.assertEqual(len(polygons), len(lines))
        canvas.destroy()


if __name__ == "__main__":
    unittest.main()
