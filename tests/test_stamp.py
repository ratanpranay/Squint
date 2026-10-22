"""A watermark stamped across the page in a grid is found, taken out of
the copy that is read, and the page's own text is left; a page without
one is left alone. And an online engine chosen for speed is not waited
for past its time; one slow page does not set the offline model's speed."""
import os
import random
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app import ocr, stamp, translator


def _font(size):
    for name in ("DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


INK = (20, 20, 20)
STAMP = (170, 170, 170)
PAPER = (250, 250, 250)


def page(w=1500, h=1700, stamped=True, every=3):
    """Lines of text, every `every`-th row written; the stamp, if any,
    at an angle in a grid of 390 by 580."""
    rnd = random.Random(7)
    img = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(img)
    y, row = 40, 0
    while y < h - 50:
        if row % every == 0:
            line = " ".join("".join(rnd.choice("abcdefghiklmnoprstuvwz")
                                    for _ in range(rnd.randint(2, 9)))
                            for _ in range(9))
            d.text((40, y), line, font=_font(30), fill=INK)
        y += 46
        row += 1
    if stamped:
        tile = Image.new("RGBA", (560, 180), (0, 0, 0, 0))
        td = ImageDraw.Draw(tile)
        td.text((10, 10), "Name 6758", font=_font(56), fill=STAMP + (255,))
        td.text((10, 90), "2026-10-20 14:37", font=_font(56),
                fill=STAMP + (255,))
        tile = tile.rotate(18, expand=True)
        for ty in range(-100, h, 390):
            for tx in range(-100, w, 580):
                img.paste(tile, (tx, ty), tile)
    return img


def count(img, colour, tol=30):
    a = np.asarray(img).astype(int)
    return int((np.abs(a - colour).sum(axis=-1) < tol).sum())


class Find(unittest.TestCase):
    def test_stamp_found(self):
        self.assertIsNotNone(stamp.find_grid(page()))

    def test_plain_page_left_alone(self):
        img = page(stamped=False, every=1)
        self.assertIsNone(stamp.find_grid(img))
        self.assertIs(stamp.cleaned(img), img)

    def test_small_picture_is_not_looked_at(self):
        self.assertIsNone(stamp.find_grid(page().crop((0, 0, 300, 300))))


class Clean(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = page()
        cls.out = stamp.cleaned(cls.img)

    def test_stamp_mostly_gone(self):
        before = count(self.img, STAMP)
        after = count(self.out, STAMP)
        self.assertLess(after, 0.4 * before)

    def test_text_kept(self):
        before = count(self.img, INK, 60)
        after = count(self.out, INK, 60)
        self.assertGreater(after, 0.9 * before)

    def test_original_untouched(self):
        self.assertGreater(count(self.img, STAMP), 0)
        self.assertIsNot(self.out, self.img)


class Snip(unittest.TestCase):
    def test_snip_uses_the_screen_it_was_cut_from(self):
        whole = page()
        box = (300, 300, 800, 800)
        snip = whole.crop(box)
        snip.info["stamp_whole"] = stamp.remember_whole(whole)
        snip.info["stamp_box"] = box
        grid, got_whole, got_box = stamp.grid_for(snip)
        self.assertIsNotNone(grid)
        self.assertIs(got_whole, whole)
        out = stamp.cleaned(snip, grid, got_whole, got_box)
        self.assertEqual(out.size, snip.size)
        self.assertLess(count(out, STAMP), 0.5 * count(snip, STAMP) + 1)

    def test_snip_keeps_where_it_came_from(self):
        from app import snip
        with open(snip.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('self.result.info["stamp_whole"]', src)


class Reading(unittest.TestCase):
    def test_read_again_without_the_stamp(self):
        seen = []
        old = ocr._image_to_lines

        def fake(img, lang=None, psm=6, source=None):
            seen.append(img)
            return [{"text": "x", "box": (0, 0, 10, 10)}] * len(seen), "t"
        ocr._image_to_lines = fake
        try:
            img = page()
            lines, used = ocr.image_to_lines(img)
        finally:
            ocr._image_to_lines = old
        self.assertEqual(len(seen), 2)
        self.assertIs(seen[0], img)
        self.assertIsNot(seen[1], img)
        self.assertEqual(len(lines), 2)

    def test_plain_page_read_once(self):
        seen = []
        old = ocr._image_to_lines

        def fake(img, lang=None, psm=6, source=None):
            seen.append(img)
            return [], "t"
        ocr._image_to_lines = fake
        try:
            ocr.image_to_lines(page(stamped=False))
        finally:
            ocr._image_to_lines = old
        self.assertEqual(len(seen), 1)


class Speed(unittest.TestCase):
    def setUp(self):
        self.old = (list(translator._speed_seen),
                    translator._hymt_speed.get("per_char"))
        translator._speed_seen[:] = []

    def tearDown(self):
        translator._speed_seen[:] = self.old[0]
        translator._hymt_speed["per_char"] = self.old[1]

    def test_one_slow_page_does_not_set_the_speed(self):
        translator._learn_speed(0.04)      # 12 s for 289 characters
        translator._learn_speed(0.002)
        self.assertEqual(translator._hymt_speed["per_char"], 0.002)
        translator._learn_speed(0.003)
        translator._learn_speed(0.05)
        translator._learn_speed(0.002)
        self.assertLessEqual(translator._hymt_speed["per_char"], 0.003)

    def test_online_engine_has_a_deadline(self):
        with open(translator.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("asked.result(timeout=ONLINE_WAIT)", src)
        self.assertIn("online_quit.set()", src)
        self.assertLessEqual(translator.ONLINE_WAIT, 3.0)


if __name__ == "__main__":
    unittest.main()
