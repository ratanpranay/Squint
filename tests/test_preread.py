"""Read ahead: a page read while you look at it is used only when the
screen there is exactly what was read."""
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402
from app import preread  # noqa: E402


def screen():
    img = Image.new("RGB", (1400, 900), "white")
    d = ImageDraw.Draw(img)
    lines = []
    for r in range(10):
        y = 50 + r * 40
        d.rectangle([100, y + 4, 700, y + 20], fill="black")
        lines.append({"text": "Zeile %d" % r, "box": (100, y, 600, 24)})
    return img, lines


def reader_with_page(img, lines, scale=1.0):
    r = preread.Reader()
    r.page = preread.Page(img, {"left": 0, "top": 0, "width": 1400,
                                "height": 900}, scale, lines, "de", None, 0.5)
    return r


class LinesForTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(preread, "enabled", lambda: True)
        p.start()
        self.addCleanup(p.stop)

    def test_same_screen_gives_the_lines_inside_moved_to_the_crop(self):
        img, lines = screen()
        r = reader_with_page(img, lines)
        box = (50, 40, 800, 250)
        got = r.lines_for(img.crop(box), box, 0, 0)
        self.assertIsNotNone(got)
        texts = [l["text"] for l in got[0]]
        self.assertEqual(texts, ["Zeile %d" % i for i in range(5)])
        self.assertEqual(got[0][0]["box"], (50, 10, 600, 24))

    def test_changed_screen_is_read_again(self):
        img, lines = screen()
        r = reader_with_page(img, lines)
        now = img.copy()
        ImageDraw.Draw(now).rectangle([0, 0, 1400, 900], fill="grey")
        box = (50, 40, 800, 250)
        self.assertIsNone(r.lines_for(now.crop(box), box, 0, 0))

    def test_a_line_cut_by_the_box_is_read_again(self):
        img, lines = screen()
        r = reader_with_page(img, lines)
        box = (50, 40, 400, 250)          # cuts every line in half
        self.assertIsNone(r.lines_for(img.crop(box), box, 0, 0))

    def test_another_monitor_is_read_again(self):
        img, lines = screen()
        r = reader_with_page(img, lines)
        box = (50, 40, 800, 250)
        self.assertIsNone(r.lines_for(img.crop(box), box, 1400, 0))

    def test_snip_origin_is_mapped_with_the_scale(self):
        img, lines = screen()
        r = reader_with_page(img, lines, scale=2.0)
        box = (100, 80, 800, 250)
        with mock.patch.object(preread, "READER", r), \
                mock.patch.object(preread, "enabled", lambda: True):
            got = preread.lines_at(img.crop(box), (50, 40), 2.0)
            off = preread.lines_at(img.crop(box), (50, 40), 1.0)
        self.assertIsNotNone(got)
        self.assertIsNone(off)

    def test_off_means_never(self):
        img, lines = screen()
        r = reader_with_page(img, lines)
        with mock.patch.object(preread, "READER", r), \
                mock.patch.object(preread, "enabled", lambda: False):
            self.assertIsNone(preread.lines_at(img, (0, 0), 1.0))

    def test_hold_to_see_leaves_cut_lines_instead_of_reading_again(self):
        img, lines = screen()
        r = reader_with_page(img, lines)
        box = (50, 40, 400, 250)
        got = r.lines_for(img.crop(box), box, 0, 0, strict=False)
        self.assertIsNotNone(got)
        self.assertEqual(got[0], [])

    def test_background_reading_never_uses_the_cloud(self):
        from app import ocr
        seen = []
        with mock.patch.object(ocr, "image_to_lines",
                               lambda img, source=None: (
                                   seen.append(ocr.ocr_choice()), ([], ""))[1]), \
                mock.patch("app.content_area.layers", lambda *a: None):
            r = preread.Reader()
            img, _ = screen()
            r._read(img, {"left": 0, "top": 0, "width": 1400,
                          "height": 900}, (1, 1), preread._thumb(img))
        self.assertEqual(seen, [ocr.OCR_LOCAL])
        self.assertNotEqual(ocr.ocr_choice(), None)

    def test_a_reading_just_begun_is_not_waited_for(self):
        img, lines = screen()
        r = reader_with_page(img, lines)
        r.page.took = 4.0                   # a 4K screen on Windows
        r.read_started = time.monotonic()
        r.reading.set()
        t0 = time.monotonic()
        self.assertIs(r.current(1.5), r.page)
        self.assertLess(time.monotonic() - t0, 0.2)

    def test_nothing_read_while_squint_shows_something(self):
        r = preread.Reader()
        grabbed = []
        with mock.patch.object(preread, "BUSY", lambda: True), \
                mock.patch.object(r, "_grab", lambda: grabbed.append(1)):
            r._look()
        self.assertEqual(grabbed, [])

    def test_key_press_read_covers_only_the_page_in_front(self):
        img, lines = screen()
        r = preread.Reader()
        layers = {"content": (50, 30, 800, 300), "window": None,
                  "monitor": (0, 0, 1400, 900)}
        from app import ocr
        with mock.patch.object(r, "_grab", lambda: (
                img, {"left": 0, "top": 0, "width": 1400, "height": 900},
                (100, 100))), \
                mock.patch("app.content_area.layers", lambda *a: layers), \
                mock.patch.object(ocr, "image_to_lines",
                                  lambda part, source=None: (
                                      [{"text": "x", "box": (5, 5, 100, 20)}],
                                      "de")):
            self.assertTrue(r.read_now())
            page = r.current(5)
        self.assertEqual(page.box, (50, 30, 850, 330))
        self.assertEqual(page.lines[0]["box"], (55, 35, 100, 20))
        # A snip outside what was read reads for itself.
        box = (0, 0, 400, 200)
        self.assertIsNone(r.lines_for(img.crop(box), box, 0, 0, wait=0))


class LookTests(unittest.TestCase):
    def test_reads_once_after_the_screen_settles(self):
        img, lines = screen()
        r = preread.Reader()
        reads = []
        with mock.patch.object(r, "_grab",
                               lambda: (img, {"left": 0, "top": 0,
                                              "width": 1400, "height": 900},
                                        (10, 10))), \
                mock.patch.object(preread, "_squint_in_front",
                                  lambda: False), \
                mock.patch.object(r, "_read",
                                  lambda *a: (reads.append(1),
                                              setattr(r, "_read_thumb",
                                                      a[3]))):
            r._look()                      # first sight: a change
            self.assertEqual(reads, [])
            r._changed_at -= 2             # a second and more later
            r._look()
            r._look()                      # same page: not read twice
        self.assertEqual(reads, [1])


if __name__ == "__main__":
    unittest.main()
