"""Zooming lays the page out once, where the gesture comes to rest, away
from the window's thread - not at every rung on the way."""
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import tkinter as tk
    from PIL import Image, ImageDraw
    from app import overlay, ui_result
    root = tk.Tk()
    root.withdraw()
except Exception:                     # pragma: no cover
    root = None


def page():
    img = Image.new("RGB", (600, 200), "white")
    draw = ImageDraw.Draw(img)
    lines = []
    for i, text in enumerate(["Die Philippinen sind ein Staat",
                              "und Archipel mit 7641 Inseln."]):
        draw.text((20, 20 + 30 * i), text, fill="black")
        lines.append({"text": text, "box": (20, 20 + 30 * i, 300, 14)})
    return img, lines


@unittest.skipIf(root is None, "no display")
class SmoothZoom(unittest.TestCase):
    def test_one_layout_per_gesture_off_the_ui_thread(self):
        img, lines = page()
        texts = ["The Philippines are a country and archipelago",
                 "with 7641 islands."]
        blocks, tall = overlay.layout(img, lines, texts, "en")
        calls = []

        def again(factor):
            calls.append((factor, threading.current_thread().name))
            time.sleep(0.3)           # a dense page
            big = img.resize((int(img.width * factor),
                              int(img.height * factor)))
            grown, grown_tall = overlay.layout(
                big, overlay.scale_lines(lines, factor), texts, "en")
            return big, grown, grown_tall

        w = ui_result.OverlayWindow(root, img, 0, 0, blocks=blocks,
                                    rerender=again, height=tall)
        try:
            # Ten notches, quickly.
            started = time.monotonic()
            for _ in range(10):
                w._roll(w.RUNGS_PER_NOTCH, when=time.monotonic())
                root.update()
                time.sleep(0.02)
            responsive = time.monotonic() - started
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and (
                    w._zoom != w._want_zoom or getattr(w, "_zoom_busy", False)):
                root.update()
                time.sleep(0.02)
            self.assertLess(responsive, 0.6)      # the window never froze
            self.assertEqual(len(calls), 1)
            self.assertNotEqual(calls[0][1], threading.current_thread().name)
            self.assertEqual(w._zoom, min(len(w.ZOOMS) - 1,
                                          int(10 * w.RUNGS_PER_NOTCH)))
        finally:
            w.close()
            root.update()


if __name__ == "__main__":
    unittest.main()
