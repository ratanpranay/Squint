"""Hold-to-see: reading order, batching, the cache, and the window
filling in as batches come back."""
import os
import queue
import sys
import threading
import time
import tkinter
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402
from app import tk_images, xray  # noqa: E402


def line(text, x, y, w=300, h=20):
    return {"text": text, "box": (x, y, w, h), "conf": 95}


class FakeTranslator:
    SPEED = "speed"

    def __init__(self):
        self.calls = []

    def translate_lines(self, texts, target="en", source="auto", job=None):
        self.calls.append(list(texts))
        return ["EN " + t for t in texts]


def page():
    """Two columns of short paragraphs on a white page."""
    img = Image.new("RGB", (1400, 900), "white")
    draw = ImageDraw.Draw(img)
    lines = []
    for col, x in enumerate((40, 760)):
        y = 40
        for para in range(4):
            for row in range(2):
                text = "Spalte %d Absatz %d Zeile %d" % (col, para, row)
                draw.text((x, y), text, fill="black")
                lines.append(line(text, x, y, 560, 18))
                y += 24
            y += 60
    return img, lines


class OrderTests(unittest.TestCase):
    def test_left_column_before_right_top_to_bottom(self):
        img, lines = page()
        groups = [[i] for i in range(len(lines))]
        ordered = xray.reading_order(lines, groups, img.width)
        texts = [lines[g[0]]["text"] for g in ordered]
        self.assertTrue(all(t.startswith("Spalte 0") for t in texts[:8]))
        self.assertTrue(all(t.startswith("Spalte 1") for t in texts[8:]))
        self.assertEqual(texts[0], "Spalte 0 Absatz 0 Zeile 0")
        self.assertEqual(texts[7], "Spalte 0 Absatz 3 Zeile 1")

    def test_first_batch_is_small(self):
        got = xray.batches(list(range(15)), first=2, most=3)
        self.assertEqual(got, [[0, 1], [2, 3, 4, 5, 6, 7],
                               [8, 9, 10, 11, 12, 13], [14]])
        self.assertEqual(xray.batches([]), [])

    def test_a_busy_page_is_still_only_four_batches(self):
        got = xray.batches(list(range(140)))
        self.assertEqual(len(got), 4)
        self.assertEqual(len(got[0]), 2)
        self.assertEqual(sum(len(b) for b in got), 140)


class CacheTests(unittest.TestCase):
    def setUp(self):
        xray._cache.clear()
        xray._cache_order.clear()

    def test_same_text_is_translated_once(self):
        fake = FakeTranslator()
        with mock.patch.object(xray, "translator", fake):
            a = xray.translate_batch([line("Hallo Welt", 0, 0)], "en", "")
            b = xray.translate_batch([line("Hallo Welt", 0, 400)], "en", "")
        self.assertEqual(a[0], ["EN Hallo Welt"])
        self.assertEqual(a, b)
        self.assertEqual(len(fake.calls), 1)

    def test_other_language_is_not_reused(self):
        fake = FakeTranslator()
        with mock.patch.object(xray, "translator", fake):
            xray.translate_batch([line("Hallo", 0, 0)], "en", "")
            xray.translate_batch([line("Hallo", 0, 0)], "fr", "")
        self.assertEqual(len(fake.calls), 2)

    def test_paragraph_numbers_unique_across_batches(self):
        a, b = [line("a", 0, 0)], [line("b", 0, 50)]
        xray._apply(a, (["A"], [0], ["A"]), 0)
        xray._apply(b, (["B"], [0], ["B"]), 1)
        self.assertNotEqual(a[0]["para"], b[0]["para"])


class ContentTests(unittest.TestCase):
    def test_only_lines_inside_the_content_area(self):
        lines = [line("tab title", 10, 5, 100, 12),
                 line("Seite eins", 10, 200, 100, 12),
                 line("Dock", 10, 880, 100, 12)]
        got = xray.inside(lines, (0, 100, 1400, 700))
        self.assertEqual([l["text"] for l in got], ["Seite eins"])
        self.assertEqual(len(xray.inside(lines, None)), 3)

    def test_given_groups_are_kept(self):
        rows = [line("Basis", 10, 10), line("Standard", 10, 40),
                line("Premium", 10, 70)]
        fake = FakeTranslator()
        texts = xray.overlay.translate_grouped(
            rows, fake, "en", groups=[[0], [1], [2]])
        self.assertEqual(texts, ["EN Basis", "EN Standard", "EN Premium"])
        self.assertEqual(fake.calls, [["Basis", "Standard", "Premium"]])

    def test_layout_steps_down_rather_than_run_off_the_bottom(self):
        img, lines = page()
        texts = ["A much longer English sentence than the German original "
                 "was, several times over, to force wrapping" for _ in lines]
        for i, ln in enumerate(lines):
            ln["para"], ln["para_text"] = i, texts[i]
        blocks, _tall = xray.fitted_layout(img, lines, texts, "en", 28, 500)
        loose, _t = xray.overlay.layout(img, lines, texts, "en", min_size=28,
                                        reach=False)
        low = max(b["cover"][3] for b in blocks)
        loose_low = max(b["cover"][3] for b in loose)
        self.assertLessEqual(low, loose_low)

    def test_text_stays_within_its_own_column(self):
        img = Image.new("RGB", (1400, 600), "white")
        draw = ImageDraw.Draw(img)
        lines = []
        for r in range(3):
            y = 40 + r * 24
            draw.rectangle([40, y + 4, 560, y + 14], fill="black")
            lines.append(dict(line("Zeile %d" % r, 40, y, 520, 18),
                              para=0, para_text="A much longer English "
                              "sentence than the original line was, " * 3))
        texts = [ln["para_text"] for ln in lines]
        region = xray.text_region(lines, (0, 0, 1400, 600))
        self.assertLess(region[2], 600)
        out = xray.paint_region(img, region, lines, texts, "en", 7)
        # Nothing painted to the right of the column.
        right = out.crop((region[2] + 2, 0, 1400, 600))
        self.assertEqual(right.getextrema(), ((255, 255),) * 3)

    def test_translation_stays_inside_the_original_lines(self):
        img = Image.new("RGB", (1400, 600), "white")
        draw = ImageDraw.Draw(img)
        lines = []
        for r in range(3):
            y = 40 + r * 24
            draw.rectangle([40, y + 4, 560, y + 14], fill="black")
            lines.append(dict(line("Zeile %d" % r, 40, y, 520, 18),
                              para=0, para_text="A much longer English "
                              "sentence than the original line was, " * 3))
        texts = [ln["para_text"] for ln in lines]
        blocks, _t = xray.fitted_layout(img, lines, texts, "en", 7, 600)
        self.assertTrue(blocks)
        for b in blocks:
            self.assertLessEqual(b["cover"][2], 40 + 520 + 6)

    def test_front_window_first_its_frame_left_out_the_rest_after(self):
        lines = [line("tab title", 10, 5, 100, 12),          # front's frame
                 line("Seite eins", 10, 200, 100, 12),       # front's page
                 line("Anderes Fenster", 1300, 400, 80, 12),  # behind
                 line("Dock", 10, 880, 100, 12)]              # Dock
        first, later = xray.arrange(
            lines, content=(0, 100, 1000, 700), window=(0, 0, 1000, 800),
            monitor=(0, 0, 1400, 860))
        self.assertEqual([l["text"] for l in first], ["Seite eins"])
        self.assertEqual([l["text"] for l in later], ["Anderes Fenster"])

    def test_line_cut_by_the_page_edge_is_left_alone(self):
        lines = [line("halbe Zeile", 10, 795, 100, 12),
                 line("ganze Zeile", 10, 400, 100, 12)]
        first, _ = xray.arrange(lines, (0, 100, 1000, 700),
                                (0, 0, 1000, 820), None, edge=3)
        self.assertEqual([l["text"] for l in first], ["ganze Zeile"])

    def test_snip_area_is_the_page_then_the_window_then_the_monitor(self):
        size = (2000, 1200)
        self.assertEqual(xray.snip_area({"area": (100, 200, 800, 600),
                                         "window": (0, 0, 1000, 900)}, size),
                         (100, 200, 900, 800))
        self.assertEqual(xray.snip_area({"area": None,
                                         "window": (0, 0, 1000, 900)}, size),
                         (0, 0, 1000, 900))
        self.assertEqual(xray.snip_area({}, size), (0, 0, 2000, 1200))

    def test_unknown_system_means_whole_screen(self):
        from app import content_area
        rect, _how = content_area.find(10, 10)
        if sys.platform not in ("darwin", "win32"):
            self.assertIsNone(rect)

class AlreadyTests(unittest.TestCase):
    def test_english_lines_are_skipped_for_english(self):
        self.assertTrue(xray.already_in("en", "Download the app for your phone"))
        self.assertFalse(xray.already_in("en", "Laden Sie die App herunter"))
        self.assertFalse(xray.already_in("en", "Whitepaper herunterladen"))
        self.assertFalse(xray.already_in("en", "汽车之家 看车 买车"))
        self.assertFalse(xray.already_in("de", "Download the app for your phone"))
        self.assertFalse(xray.already_in("en", "Home"))


class Controller:
    def __init__(self, root):
        self.root = root
        self.queue = queue.Queue()
        self.busy = threading.Lock()


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tkinter.Tk()
        cls.root.withdraw()
        tk_images.install()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        xray._cache.clear()
        xray._cache_order.clear()
        self.img, self.lines = page()
        self.ctl = Controller(self.root)
        self.x = xray.XRay(self.ctl)
        shot = {"image": self.img, "left": 0, "top": 0, "width": 1400,
                "height": 900, "scale": 1.0}
        self.patches = [
            mock.patch.object(self.x, "_capture", lambda: shot),
            mock.patch.object(xray.ocr, "image_to_lines",
                              lambda img, source=None: (
                                  [dict(ln) for ln in self.lines], "de")),
            mock.patch.object(xray, "translator", FakeTranslator()),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        self.x.close()
        for p in self.patches:
            p.stop()

    def pump(self, seconds=5.0):
        frames = []
        end = time.time() + seconds
        while time.time() < end:
            self.root.update()
            try:
                action, payload = self.ctl.queue.get(timeout=0.02)
            except queue.Empty:
                continue
            if action == "xray_frame":
                self.x.frame(payload)
                frames.append(payload)
                if payload[3] == "" and payload[1] is not None:
                    break
        return frames

    def keys(self, key, mods):
        self.state = {"key": key, "mods": mods}
        return [mock.patch.object(xray.keystate, "is_down",
                                  lambda spec: self.state["key"]),
                mock.patch.object(xray.keystate, "modifiers_down",
                                  lambda spec: self.state["mods"])]

    def run_for(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.root.update()

    def held(self, key=True, mods=True):
        patches = self.keys(key, mods)
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])

    def test_translates_the_page_the_way_a_snip_does(self):
        self.held()
        calls = []
        real = xray.overlay.translate_grouped

        def spy(lines, *a, **k):
            calls.append(len(lines))
            return real(lines, *a, **k)
        with mock.patch.object(xray.overlay, "translate_grouped", spy):
            self.x.press("ctrl+alt+x")
            frames = self.pump()
        pictures = [f for f in frames if f[1] is not None]
        self.assertEqual(len(pictures), 1)          # one result, as a snip
        self.assertEqual(calls, [len(self.lines)])  # one translation, whole
        self.assertTrue(pictures[-1][1])
        self.assertTrue(self.x.canvas.find_withtag("tx"))
        self.assertEqual(frames[-1][3], "")

    def test_stays_while_ctrl_alt_held_and_closes_on_release(self):
        self.held()
        self.x.press("ctrl+alt+x")
        self.run_for(0.3)
        self.state["key"] = False          # X up, Ctrl+Alt still down
        self.run_for(0.3)
        self.assertIsNotNone(self.x.win)
        self.state["mods"] = False         # everything up
        self.run_for(0.3)
        self.assertIsNone(self.x.win)

    def test_x_twice_freezes_until_pressed_again(self):
        self.held()
        self.x.press("ctrl+alt+x")
        self.run_for(0.2)
        self.state["key"] = False
        self.run_for(0.2)
        self.state["key"] = True
        self.x.press("ctrl+alt+x")         # the second X
        self.assertTrue(self.x.sticky)
        self.state.update(key=False, mods=False)
        self.run_for(0.3)
        self.assertIsNotNone(self.x.win)   # frozen: stays
        self.x.press("ctrl+alt+x")
        self.assertIsNone(self.x.win)

    def test_auto_repeat_does_not_freeze(self):
        self.held()
        self.x.press("ctrl+alt+x")
        self.run_for(0.2)
        self.x.press("ctrl+alt+x")         # X never came up: a repeat
        self.assertFalse(self.x.sticky)
        self.assertIsNotNone(self.x.win)

    def test_escape_closes_a_frozen_view(self):
        self.held()
        self.x.press("ctrl+alt+x")
        self.run_for(0.2)
        self.x._make_sticky()
        self.x.win.event_generate("<Escape>")
        self.run_for(0.1)
        self.assertIsNone(self.x.win)

    def test_unknown_key_state_leaves_it_up(self):
        self.held(key=None, mods=None)
        self.x.press("ctrl+alt+x")
        self.run_for(0.3)
        self.assertTrue(self.x.sticky)
        self.assertIsNotNone(self.x.win)


    def test_retina_capture_is_laid_out_at_screen_size(self):
        big = self.img.resize((2800, 1800))
        shot = {"image": big, "left": 0, "top": 0, "width": 1400,
                "height": 900, "scale": 2.0, "area": (0, 0, 2800, 1800)}
        doubled = []
        for ln in self.lines:
            x, y, w, h = ln["box"]
            doubled.append(dict(ln, box=(2 * x, 2 * y, 2 * w, 2 * h)))
        self.held()
        with mock.patch.object(self.x, "_capture", lambda: shot), \
                mock.patch.object(xray.ocr, "image_to_lines",
                                  lambda img, source=None: (
                                      [dict(d) for d in doubled], "de")):
            self.x.press("ctrl+alt+x")
            frames = self.pump()
        pictures = [f for f in frames if f[1] is not None]
        self.assertTrue(pictures)
        # Laid out at the captured resolution, drawn at screen size.
        blocks = pictures[-1][1]
        self.assertGreater(max(b["cover"][2] for b in blocks), 1400)
        for item in self.x.canvas.find_withtag("tx"):
            x, y = self.x.canvas.coords(item)[:2]
            self.assertLessEqual(x, 1400)
            self.assertLessEqual(y, 900)


    def test_main_window_is_hidden_and_put_back(self):
        main = tkinter.Toplevel(self.root)
        main.geometry("200x100+10+10")
        self.run_for(0.2)
        self.ctl.window = main
        self.x._hide_main()
        self.assertEqual(float(main.attributes("-alpha")), 0.0)
        self.x._show_main()
        self.run_for(0.5)
        self.assertEqual(float(main.attributes("-alpha")), 1.0)
        main.destroy()

    def test_second_look_comes_from_the_cache(self):
        fake = xray.translator
        self.held()
        self.x.press("ctrl+alt+x")
        self.pump()
        calls = len(fake.calls)
        self.x.close()
        self.x.press("ctrl+alt+x")
        self.pump()
        self.assertEqual(len(fake.calls), calls)

    def test_not_while_a_snip_is_being_picked(self):
        self.ctl.busy.acquire()
        try:
            self.x.press("ctrl+alt+x")
            self.assertIsNone(self.x.win)
        finally:
            self.ctl.busy.release()


if __name__ == "__main__":
    unittest.main()
