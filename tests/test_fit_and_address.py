"""A sentence that mentions a web address is translated; a row is never
drawn wider than its cover."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import overlay  # noqa: E402

try:
    import tkinter as tk
    import tkinter.font as tkfont
    from PIL import Image
    from app import ui_result
    root = tk.Tk()
    root.withdraw()
except Exception:                     # pragma: no cover
    root = None


class Address(unittest.TestCase):
    def test_sentence_with_a_domain_is_translated(self):
        self.assertFalse(overlay.carries_an_address(
            "Die Garantie gilt für jeden Artikel, der über shop-example.de, "
            "die App oder einen deutschen Store erworben wurde"))

    def test_address_lines_are_held(self):
        for t in ("E-Mail: info@firma.de", "www.example.com/kontakt",
                  "Kontakt: service@firma.de oder Tel. 0800 123"):
            self.assertTrue(overlay.carries_an_address(t), t)


@unittest.skipIf(root is None, "no display")
class NeverWider(unittest.TestCase):
    def test_row_fits_its_cover(self):
        img = Image.new("RGB", (400, 120), "white")
        row = "A long translated row that the layout measured too narrow"
        block = {"cover": (10, 10, 210, 50), "bg": (255, 255, 255),
                 "fg": (0, 0, 0), "size": 24, "x": 12, "y": 12,
                 "kind": "default", "leading": 28, "right": 208,
                 "rtl": False, "cell": False, "rows": [row], "lines": 1}
        w = ui_result.OverlayWindow(root, img, 0, 0, blocks=[block],
                                    height=120)
        try:
            root.update()
            items = [i for i in w.canvas.find_withtag("tx")
                     if w.canvas.type(i) == "text"]
            x0, _y0, x1, _y1 = w.canvas.bbox(items[0])
            self.assertLessEqual(x1 - x0, 200 + 4)
        finally:
            w.close()
            root.update()


if __name__ == "__main__":
    unittest.main()
