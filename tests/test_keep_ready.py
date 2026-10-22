"""A cancelled or dismissed snip is not wasted: its work finishes in the
background and makes the next snip there quick."""
import os
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402
from app import main, preread, translator  # noqa: E402


class Toast:
    def __init__(self, key=("k",)):
        self.cancelled = False
        self.closed = False
        self.job_key = key

    def close(self):
        self.closed = True


class Queue:
    def __init__(self):
        self.items = []

    def put(self, item):
        self.items.append(item)


class Fake:
    cancel_snip = main.Controller.cancel_snip
    _drop_part = staticmethod(main.Controller._drop_part)
    _landing = main.Controller._landing
    _reuse_cancelled = main.Controller._reuse_cancelled
    _settle_detached = main.Controller._settle_detached

    def __init__(self):
        self.busy = threading.Lock()
        self.queue = Queue()
        self.xray = None


def running(c, key=("k",)):
    c.busy.acquire()
    toast = Toast(key)
    job = main._SnipJob(key, toast, threading.Event())
    job.area = (0, 0, 400, 300)
    c._snip_toast, c._snip_stop, c._snip_job = toast, job.stop, job
    return toast, job


class LandingTests(unittest.TestCase):
    def test_result_of_a_cancelled_snip_is_kept_and_shown_next_time(self):
        c = Fake()
        old, job = running(c)
        c.cancel_snip()
        self.assertIsNone(c._landing("overlay", (old, "picture", (1, 2))))
        new = Toast()
        self.assertTrue(c._reuse_cancelled(new))
        action, payload = c.queue.items[-1]
        self.assertEqual(action, "overlay")
        self.assertIs(payload[0], new)
        self.assertEqual(payload[1:], ("picture", (1, 2)))

    def test_other_area_is_not_given_the_kept_result(self):
        c = Fake()
        old, job = running(c)
        c.cancel_snip()
        c._landing("overlay", (old, "picture"))
        self.assertFalse(c._reuse_cancelled(Toast(("other",))))

    def test_snip_again_while_it_still_works_picks_it_up(self):
        c = Fake()
        old, job = running(c)
        c.cancel_snip()
        new = Toast()
        self.assertTrue(c._reuse_cancelled(new))
        self.assertIs(job.toast, new)
        c._snip_toast = new
        # A result queued with the old indicator lands on the new one.
        got = c._landing("snip_done", (old, "text", "orig", "meta"))
        self.assertIs(got[0], new)

    def test_new_snip_never_waits_and_stops_the_old_one(self):
        c = Fake()
        old, job = running(c)
        c.cancel_snip()
        img = Image.new("RGB", (300, 200))
        waits = c._settle_detached((50, 50), img, 1.0)
        self.assertEqual(waits, [])
        self.assertTrue(job.stop.is_set())


class BlockTests(unittest.TestCase):
    def setUp(self):
        translator._blocks.clear()

    def run_twice(self, first, second, engine_then="hymt",
                  engine_now="hymt"):
        sent = []
        engine = {"now": engine_then}

        def inner(lines, target, source, job, blocks):
            sent.append(list(lines))
            return ["EN " + l for l in lines]
        with mock.patch.object(translator, "_translate_lines", inner), \
                mock.patch("app.config.CONFIG.get",
                           lambda k, d=None: engine["now"]
                           if k == "last_backend" else d), \
                mock.patch.object(translator, "_lead_engine",
                                  lambda job=None: engine["now"]):
            a = translator.translate_lines(first, "en", blocks=True)
            engine["now"] = engine_now
            b = translator.translate_lines(second, "en", blocks=True)
        return a, b, sent

    S1 = "Das ist der erste ganze Satz hier."
    S2 = "Und das ist ein zweiter ganzer Satz."
    S3 = "Ein dritter Satz kommt noch dazu."

    def test_sentences_translated_minutes_ago_are_not_sent_again(self):
        a, b, sent = self.run_twice([self.S1, self.S2], [self.S2, self.S3])
        self.assertEqual(b, ["EN " + self.S2, "EN " + self.S3])
        self.assertEqual(sent, [[self.S1, self.S2], [self.S3]])

    def test_short_labels_are_always_translated_with_their_page(self):
        _a, _b, sent = self.run_twice(["Bank", "报价"], ["Bank", "报价"])
        self.assertEqual(sent, [["Bank", "报价"], ["Bank", "报价"]])

    def test_long_cjk_sentence_is_reused(self):
        cjk = "这是一个很长的中文句子用来测试是否可以再次使用"
        _a, _b, sent = self.run_twice([cjk], [cjk])
        self.assertEqual(sent, [[cjk]])

    def test_only_the_same_engine_s_answers_are_reused(self):
        _a, _b, sent = self.run_twice([self.S1], [self.S1],
                                      engine_then="hymt", engine_now="groq")
        self.assertEqual(sent, [[self.S1], [self.S1]])

    def test_kept_only_for_a_few_minutes(self):
        translator._block_put("en", [("ein alter Satz mit genug Worten", "old")], "hymt")
        with mock.patch.object(translator, "BLOCK_KEEP", -1):
            self.assertIsNone(translator._block_get(
                "en", "ein alter Satz mit genug Worten"))

    def test_background_uses_this_computer_only(self):
        translator.set_background(True)
        try:
            with mock.patch("app.offline_model.ready", lambda: False):
                with self.assertRaises(translator.Cancelled):
                    translator.translate_lines(["x"], "en", blocks=True)
            with mock.patch("app.offline_model.ready", lambda: True), \
                    mock.patch("app.offline_model.translate_lines",
                               lambda lines, *a, **k: ["L " + l
                                                       for l in lines]), \
                    mock.patch.object(translator, "_online_lines",
                                      side_effect=AssertionError("online")):
                out = translator.translate_lines(["y"], "en", blocks=True)
            self.assertEqual(out, ["L y"])
        finally:
            translator.set_background(False)


def page():
    img = Image.new("RGB", (800, 600), "white")
    d = ImageDraw.Draw(img)
    lines = []
    for r in range(10):
        y = 20 + r * 50
        d.rectangle([40, y + 4, 700, y + 20], fill="black")
        lines.append({"text": "line %d" % r, "box": (40, y, 660, 24)})
    return img, lines


class SnipReadingTests(unittest.TestCase):
    def setUp(self):
        self.old = preread.READER
        preread.READER = preread.Reader()
        self.addCleanup(lambda: setattr(preread, "READER", self.old))

    def test_a_snip_inside_the_last_one_reuses_its_reading(self):
        img, lines = page()
        preread.remember_snip(img, (100, 100), 1.0, lines, "de")
        box = (0, 60, 800, 310)               # lines 1-5 whole
        got = preread.lines_at(img.crop(box), (100 + box[0], 100 + box[1]),
                               1.0)
        self.assertIsNotNone(got)
        self.assertEqual([l["text"] for l in got[0]][:2],
                         ["line 1", "line 2"])

    def test_a_few_cut_lines_are_read_again_not_everything(self):
        img, lines = page()
        preread.remember_snip(img, (0, 0), 1.0, lines, "de")
        box = (0, 30, 800, 310)       # cuts line 0 (20-44) at the top
        calls = []

        def read(pic, source=None):
            calls.append(pic.size)
            return [{"text": "fresh", "box": (40, 0, 660, 14)}], "de"
        with mock.patch("app.ocr.image_to_lines", read):
            got = preread.lines_at(img.crop(box), (0, 30), 1.0)
        self.assertIsNotNone(got)
        self.assertEqual(len(calls), 1)
        self.assertLess(calls[0][1], 60)          # only those rows
        texts = [l["text"] for l in got[0]]
        self.assertEqual(texts[0], "fresh")
        self.assertIn("line 5", texts)


if __name__ == "__main__":
    unittest.main()


class EscTests(unittest.TestCase):
    def test_esc_cancels_only_after_being_seen_up(self):
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        c = Fake()
        c.root = root
        c._watch_esc = main.Controller._watch_esc.__get__(c)
        toast, job = running(c)
        started = time.time()
        # Held from before (the Esc that closed something else): ignored
        # until it is let go and pressed again.
        with mock.patch("app.keystate.is_down",
                        lambda spec: time.time() - started < 0.2
                        or time.time() - started > 0.4):
            c._watch_esc(toast)
            end = time.time() + 0.3
            while time.time() < end:
                root.update()
            self.assertFalse(toast.cancelled)
            end = time.time() + 0.4
            while time.time() < end:
                root.update()
        self.assertTrue(toast.cancelled)


class PreparedTests(unittest.TestCase):
    def test_hold_waits_for_the_page_being_prepared(self):
        from app import xray
        key = ("page", "en", "", "abc")
        done = threading.Event()
        with xray._preparing_lock:
            xray._preparing[key] = done

        def finish():
            xray._cache_put(key, ["blocks"])
            with xray._preparing_lock:
                xray._preparing.pop(key, None)
            done.set()
        threading.Timer(0.1, finish).start()
        self.assertEqual(xray._wait_prepared(key, wait=2), ["blocks"])
        self.assertIsNone(xray._wait_prepared(("page", "x"), wait=2))
