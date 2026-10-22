"""A page that keeps moving (a banner) is read again only where it moved,
and a snip does not wait for a whole-page Hy-MT2 run to fill one line."""
import os
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402
from app import preread, translator  # noqa: E402


def page():
    img = Image.new("RGB", (1400, 900), "white")
    d = ImageDraw.Draw(img)
    lines = []
    for r in range(15):
        y = 50 + r * 50
        d.rectangle([100, y + 4, 700, y + 20], fill="black")
        lines.append({"text": "old %d" % r, "box": (100, y, 600, 24)})
    return img, lines


def banner(img):
    now = img.copy()
    ImageDraw.Draw(now).rectangle([900, 300, 1300, 330], fill="red")
    return now


def fake_read(pic):
    return [{"text": "new", "box": (900, 5, 400, 20)}]


class BandTests(unittest.TestCase):
    def test_nothing_changed(self):
        img, _ = page()
        self.assertEqual(preread.changed_bands(img, img.copy()), [])

    def test_only_the_banner_rows(self):
        img, _ = page()
        bands = preread.changed_bands(img, banner(img))
        self.assertEqual(len(bands), 1)
        top, bottom = bands[0]
        self.assertTrue(296 <= top <= 300 and 330 <= bottom <= 336, bands)

    def test_widened_to_whole_lines(self):
        _, lines = page()
        # A band touching the line at y=300..324 grows to take it whole.
        got = preread.widen_bands([(310, 320)], lines, 900, pad=0)
        self.assertEqual(got, [(300, 324)])

    def test_reread_keeps_the_rest(self):
        img, lines = page()
        now = banner(img)
        bands = preread.widen_bands(preread.changed_bands(img, now),
                                    lines, now.height)
        out, count = preread.reread_bands(now, lines, bands, fake_read)
        self.assertEqual(count, 1)
        texts = [l["text"] for l in out]
        self.assertIn("new", texts)
        self.assertEqual(len(texts), 15)       # one old line replaced
        self.assertNotIn("old 5", texts)
        self.assertEqual(texts.index("new"), 5)


class LinesForTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(preread, "enabled", lambda: True)
        p.start()
        self.addCleanup(p.stop)

    def reader(self, img, lines):
        r = preread.Reader()
        r.page = preread.Page(img, {"left": 0, "top": 0, "width": 1400,
                                    "height": 900}, 1.0, lines, "zh", None,
                              0.5)
        return r

    def test_snip_reads_only_the_banner(self):
        img, lines = page()
        r = self.reader(img, lines)
        now = banner(img)
        box = (0, 0, 1400, 900)
        with mock.patch("app.ocr.image_to_lines",
                        lambda pic, source=None: (fake_read(pic), "zh")):
            got = r.lines_for(now.crop(box), box, 0, 0)
        self.assertIsNotNone(got)
        self.assertIn("new", [l["text"] for l in got[0]])

    def test_whole_page_changed_is_not_used(self):
        img, lines = page()
        r = self.reader(img, lines)
        now = img.copy()
        ImageDraw.Draw(now).rectangle([0, 0, 1400, 900], fill="grey")
        box = (0, 0, 1400, 900)
        self.assertIsNone(r.lines_for(now.crop(box), box, 0, 0))

    def test_background_patch(self):
        img, lines = page()
        r = self.reader(img, lines)
        now = banner(img)
        with mock.patch("app.ocr.image_to_lines",
                        lambda pic, source=None: (fake_read(pic), "zh")):
            done = r._patch(now, {"left": 0, "top": 0, "width": 1400,
                                  "height": 900}, preread._thumb(now))
        self.assertTrue(done)
        self.assertIs(r.page.image, now)
        self.assertIn("new", [l["text"] for l in r.page.lines])
        self.assertFalse(r.reading.is_set())


class FillTests(unittest.TestCase):
    def setUp(self):
        translator._blocks.clear()

    def test_missing_line_does_not_wait_for_the_whole_page(self):
        slow_cancel = threading.Event()

        def slow_page(*a, **k):
            slow_cancel.wait(10)
            return ["x"] * 3

        future_holder = {}

        def beside(lines, target, job, whole=False):
            import concurrent.futures as f
            pool = f.ThreadPoolExecutor(1)
            fut = pool.submit(slow_page)
            future_holder["f"] = fut
            return fut, slow_cancel

        with mock.patch.object(translator, "_hymt_lines",
                               lambda *a, **k: None), \
                mock.patch.object(translator, "_hymt_beside", beside), \
                mock.patch.object(translator, "_online_lines",
                                  lambda *a, **k: ["A", "", "C"]), \
                mock.patch("app.offline_model.translate_lines",
                           lambda lines, *a, **k: ["B!"] * len(lines)):
            started = time.time()
            out = translator.translate_lines(["a", "b", "c"], "en",
                                             blocks=True)
        self.assertEqual(out, ["A", "B!", "C"])
        self.assertLess(time.time() - started, 2.0)
        self.assertTrue(slow_cancel.is_set())


if __name__ == "__main__":
    unittest.main()
