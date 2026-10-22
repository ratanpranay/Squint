"""Faster and better translation: nothing sent that needs no translating,
repeats once, short labels together with context, dense pages in parallel,
the page shown as it fills in, and the screen read at a size that suits."""
import json
import os
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402
from app import offline_model, overlay, translator  # noqa: E402


class SkipTests(unittest.TestCase):
    def test_same_in_every_language(self):
        for text in ("12,50 €", "9:00–20:30", "14.11.2025", "E-104",
                     "NR-48213", "500 mg", "38 W", "420 m³/h", "15 h",
                     "info@example.com", "www.example.com", "70%",
                     "DE12 3456 7890 1234 5678 90", "XC60"):
            self.assertTrue(translator.needs_no_translation(text), text)

    def test_words_are_translated(self):
        for text in ("Cerrado", "a", "Sábados", "Bank", "报价", "주말 날씨",
                     "Monday", "Hall 3", "Gleis 7"):
            self.assertFalse(translator.needs_no_translation(text), text)


class BlocksTests(unittest.TestCase):
    def setUp(self):
        translator._blocks.clear()

    def test_kept_repeats_once_and_progress(self):
        sent, told = [], {}

        def inner(lines, target, source, job, blocks):
            sent.append(list(lines))
            ctx = translator._context()
            self.assertIsNotNone(ctx)
            fn = translator._progress()
            out = []
            for i, l in enumerate(lines):
                out.append("EN " + l)
                fn(i, out[-1])
            return out
        with mock.patch.object(translator, "_translate_lines", inner):
            out = translator.translate_lines(
                ["Preis", "12,50 €", "Preis", "Kaufen"], "en", blocks=True,
                progress=lambda i, t: told.setdefault(i, t))
        self.assertEqual(out, ["EN Preis", "12,50 €", "EN Preis",
                               "EN Kaufen"])
        self.assertEqual(sent, [["Preis", "Kaufen"]])
        self.assertEqual(sorted(told), [0, 1, 2, 3])


class OfflineTests(unittest.TestCase):
    def run_lines(self, lines, listed=True):
        calls = []

        def as_list(items, target):
            calls.append(("list", list(items)))
            return ["L " + i for i in items] if listed else None

        def one(text, target):
            calls.append(("one", text))
            return "O " + text

        def ctx(text, target, context):
            calls.append(("ctx", text, context))
            return "C " + text
        told = []
        with mock.patch.object(offline_model, "_ensure_running",
                               lambda: None), \
                mock.patch.object(offline_model, "translate_list", as_list), \
                mock.patch.object(offline_model, "translate", one), \
                mock.patch.object(offline_model, "translate_with_context",
                                  ctx), \
                mock.patch.dict(offline_model._server, {"slots": 1}):
            out = offline_model.translate_lines(
                lines, "en", whole=True, workers=1,
                progress=lambda i, t: told.append(i),
                context={"Kaufen": "Preis / Versand"})
        return out, calls, told

    def test_labels_one_at_a_time_with_their_neighbours(self):
        lines = ["Preis", "Versand", "Das ist ein langer Satz über Dinge.",
                 "Kaufen"]
        out, calls, told = self.run_lines(lines)
        self.assertNotIn("list", [c[0] for c in calls])
        self.assertIn(("ctx", "Kaufen", "Preis / Versand"), calls)
        # Every item told; longest started first (not page order).
        self.assertEqual(sorted(told), [0, 1, 2, 3])
        self.assertEqual(out[3], "C Kaufen")

    def test_list_parsing(self):
        with mock.patch.object(offline_model, "_ask",
                               lambda c, b: "1. Price\n2) Shipping\n3、Buy"):
            self.assertEqual(offline_model.translate_list(
                ["Preis", "Versand", "Kaufen"], "en"),
                ["Price", "Shipping", "Buy"])
        with mock.patch.object(offline_model, "_ask",
                               lambda c, b: "1. Price\n3. Buy"):
            self.assertIsNone(offline_model.translate_list(
                ["Preis", "Versand", "Kaufen"], "en"))

    def test_context_answer_that_took_the_context_in_is_not_used(self):
        with mock.patch.object(offline_model, "_ask",
                               lambda c, b: "Job advert: apply"), \
                mock.patch.object(offline_model, "translate",
                                  lambda t, g: "Apply"):
            self.assertEqual(offline_model.translate_with_context(
                "Postuler", "en", "Job advert / Save"), "Apply")


class OnlineTests(unittest.TestCase):
    def test_dense_page_in_parallel_chunks(self):
        lines = ["Zeile %d mit etwas Text" % i for i in range(120)]
        active, most = [0], [0]
        lock = threading.Lock()

        def one(chunk, target, source, job):
            with lock:
                active[0] += 1
                most[0] = max(most[0], active[0])
            time.sleep(0.2)
            with lock:
                active[0] -= 1
            return ["EN " + l for l in chunk]
        told = []
        translator._job.progress = lambda i, t: told.append(i)
        try:
            with mock.patch.object(translator, "_online_lines_one", one):
                started = time.time()
                out = translator._online_lines(lines, "en", "auto", None)
        finally:
            translator._job.progress = None
        self.assertEqual(out[5], "EN " + lines[5])
        self.assertGreaterEqual(most[0], 2)
        self.assertLess(time.time() - started, 0.2 * 3)
        self.assertEqual(sorted(told), list(range(120)))


class GeminiTests(unittest.TestCase):
    def test_thinking_off(self):
        body = json.dumps({"generationConfig": {"temperature": 0}})
        got = json.loads(translator._thinking_off(body, "gemini-2.5-flash"))
        self.assertEqual(got["generationConfig"]["thinkingConfig"],
                         {"thinkingBudget": 0})
        self.assertIs(translator._thinking_off(body, "gemini-2.5-pro"), body)
        got = json.loads(translator._thinking_off(body, "gemini-3-flash"))
        self.assertIn("thinkingLevel", got["generationConfig"]["thinkingConfig"])


class FakeTranslator:
    SPEED = "speed"

    def translate_lines(self, lines, target="en", source="auto", job=None,
                        blocks=False, progress=None):
        out = []
        for i, line in enumerate(lines):
            time.sleep(0.15)
            out.append("EN " + line)
            if progress:
                progress(i, out[-1])
        return out

    def translate(self, text, **kw):
        return "EN " + text


class ProgressiveTests(unittest.TestCase):
    def test_page_shown_as_it_fills_in_top_first(self):
        img = Image.new("RGB", (900, 700), "white")
        d = ImageDraw.Draw(img)
        lines = []
        for r in range(6):
            y = 40 + r * 100
            d.rectangle([40, y + 4, 500, y + 22], fill="black")
            lines.append({"text": "Absatz Nummer %d hier" % r,
                          "box": (40, y, 460, 26)})
        partials = []
        texts, blocks, tall = overlay.progressive(
            img, lines, FakeTranslator(), "en", "auto", 8,
            shown=lambda b, t: partials.append(b), every=0.2)
        self.assertTrue(partials)
        first = partials[0]
        self.assertLess(len(first), len(blocks))
        self.assertEqual(min(b["para"] for b in first), 0)
        self.assertEqual(len(blocks), 6)
        self.assertTrue(all(t.startswith("EN ") for t in texts))


class ReadSizeTests(unittest.TestCase):
    def test_big_screen_read_at_half_when_text_is_big_enough(self):
        from app import ocr_windows
        img = Image.new("RGB", (3840, 2160), "white")
        seen = []

        def read(tag, bitmap):
            seen.append(bitmap)
            return [{"text": "x", "box": (10, 10, 100, 16)}]
        with mock.patch.object(ocr_windows, "_read_with", read), \
                mock.patch.object(ocr_windows, "_software_bitmap",
                                  lambda im: im.size):
            factor, readings, done = ocr_windows._reading_size(
                img, ["de-DE", "ja"])
        self.assertEqual(factor, 0.5)
        self.assertEqual(seen, [(1920, 1080)])
        self.assertEqual(readings[0][1][0]["box"], (20, 20, 200, 32))

    def test_small_text_is_read_enlarged(self):
        from app import ocr_windows
        img = Image.new("RGB", (400, 120), "white")
        with mock.patch.object(ocr_windows, "_read_with",
                               lambda t, b: [{"text": "x",
                                              "box": (0, 0, 50, 8)}]), \
                mock.patch.object(ocr_windows, "_software_bitmap",
                                  lambda im: im.size):
            factor, readings, done = ocr_windows._reading_size(img, ["de"])
        self.assertEqual(factor, 2.0)
        self.assertEqual(readings, [])


if __name__ == "__main__":
    unittest.main()
