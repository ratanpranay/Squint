"""Text on photographs: headlines in capitals are translated, labels the
engine handed back are asked again, letters seen in a photo are left out,
covers are the picture softened, labels move one by one; and the panel is
kept on the screen."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw

from app import ocr, overlay, ui_panel


class Capitals(unittest.TestCase):
    def test_shouting(self):
        self.assertTrue(overlay._shouting("HANDTELLERGROSSES DESIGN"))
        self.assertFalse(overlay._shouting("USB-C"))
        self.assertFalse(overlay._shouting("Ein ganz normaler Satz"))
        self.assertFalse(overlay._shouting("ABC DEF"))

    def test_sent_in_sentence_case_and_put_back(self):
        sent = []

        class Engine:
            def translate_lines(self, texts, **kw):
                sent.extend(texts)
                return ["Hand-sized design" for _ in texts]
        lines = [{"text": "HANDTELLERGROSSES DESIGN", "box": (10, 10, 400, 40)}]
        out = overlay.translate_grouped(lines, Engine(), "en")
        self.assertEqual(sent, ["Handtellergrosses design"])
        self.assertEqual(out[0], "HAND-SIZED DESIGN")


class LeftAsTheyWere(unittest.TestCase):
    def test_figures_are_not_failures(self):
        lines = [{"text": "25-40PSI", "para": 0, "para_text": "25-40PSI",
                  "box": (0, 0, 100, 30)},
                 {"text": "Motorrad", "para": 1, "para_text": "Motorcycle",
                  "box": (0, 40, 100, 30)},
                 {"text": "Fahrrad", "para": 2, "para_text": "Fahrrad",
                  "box": (0, 80, 100, 30)}]
        left, judged = overlay.left_as_they_were(lines)
        self.assertEqual(left, 1)
        self.assertGreaterEqual(judged, 2)


class Retry(unittest.TestCase):
    def test_label_handed_back_is_asked_again(self):
        from app import offline_model
        with open(offline_model.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("plain = translate(text, target)", src)
        self.assertIn("not text.strip()[:1].islower()", src)
        self.assertIn("sum(1 for c in text if c.isalpha()) >= 2", src)


def photo(size=(600, 300), seed=3):
    import random
    rnd = random.Random(seed)
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(size[1]):
        for x in range(size[0]):
            v = rnd.randint(0, 255)
            px[x, y] = (v, rnd.randint(0, 255), 255 - v)
    return img


class Stray(unittest.TestCase):
    def test_letters_in_a_photo_dropped(self):
        img = Image.new("RGB", (800, 600), "white")
        img.paste(photo((300, 100)), (400, 400))
        lines = [{"text": "Ein ganz normaler Satz hier", "box": (20, 20 + 40 * i,
                                                                 360, 24)}
                 for i in range(5)]
        lines.append({"text": u"日本語文字", "box": (450, 430, 160, 30)})
        kept = ocr.drop_stray_script(lines, img)
        self.assertEqual(len(kept), 5)

    def test_kept_on_plain_paper(self):
        img = Image.new("RGB", (800, 600), "white")
        lines = [{"text": "Ein ganz normaler Satz hier", "box": (20, 20 + 40 * i,
                                                                 360, 24)}
                 for i in range(5)]
        lines.append({"text": u"日本語文字", "box": (450, 430, 160, 30)})
        self.assertEqual(len(ocr.drop_stray_script(lines, img)), 6)


class Patch(unittest.TestCase):
    def test_soft_patch(self):
        img = photo()
        patch, ink = overlay.soft_patch(img, (100, 100, 300, 140), 40)
        self.assertEqual(patch.size, (200, 40))
        self.assertEqual(patch.mode, "RGBA")
        self.assertLess(patch.getpixel((0, 0))[3], 255)       # fades out
        self.assertEqual(patch.getpixel((100, 20))[3], 255)
        self.assertIn(ink, ((255, 255, 255), (20, 20, 22)))

    def test_too_small_is_none(self):
        self.assertEqual(overlay.soft_patch(photo(), (0, 0, 2, 2), 10),
                         (None, None))


class Labels(unittest.TestCase):
    def test_picture_flag_survives_paragraphs(self):
        with open(overlay.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('"pictured": all(p.get("pictured") for p in picked)',
                      src)

    def test_labels_on_a_picture_do_not_cover_their_figures(self):
        img = photo((900, 300))
        draw = ImageDraw.Draw(img)
        draw.rectangle((90, 40, 300, 140), fill=(30, 30, 30))
        draw.rectangle((590, 40, 860, 140), fill=(30, 30, 30))
        lines = [{"text": "Benutzerdefinierter", "box": (600, 50, 250, 40)},
                 {"text": "Motorrad", "box": (100, 60, 150, 40)},
                 {"text": "Bereich", "box": (640, 88, 120, 40)},
                 {"text": "25-40PSI", "box": (110, 102, 120, 30)}]
        texts = ["Custom", "Motorcycle", "Area", "25-40PSI"]
        for i, line in enumerate(lines):
            line["para"], line["para_text"] = i, texts[i]
        blocks, _tall = overlay.layout(img, lines, texts, "en")
        moto = [b for b in blocks if "Motorcycle" in " ".join(b["rows"])][0]
        # Not pushed down onto the figures under it by "Bereich".
        self.assertLessEqual(moto["cover"][1], 62)


class Panel(unittest.TestCase):
    def test_kept_above_the_taskbar(self):
        x, y = ui_panel.place(300, 400, (1800, 1060), (0, 0, 1920, 1080),
                              work=(0, 0, 1920, 1040))
        self.assertLessEqual(y + 400, 1040)
        self.assertLessEqual(x + 300, 1920)

    def test_windows_placement_wired(self):
        self.assertTrue(hasattr(ui_panel.MiniPanel, "_place_windows"))
        if sys.platform != "win32":
            self.assertEqual(ui_panel._windows_monitor(None), (None, None))


if __name__ == "__main__":
    unittest.main()


class NoReadAhead(unittest.TestCase):
    """The background reading is gone, whatever an old setting says."""

    def test_off_even_when_switched_on(self):
        from app import config, preread
        old = config.CONFIG.get("read_ahead")
        try:
            config.CONFIG["read_ahead"] = True
            self.assertFalse(preread.enabled())
        finally:
            config.CONFIG["read_ahead"] = old

    def test_app_does_not_start_it(self):
        from app import main
        with open(main.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("preread.start()", src)
