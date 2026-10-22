"""A tap of the shortcut is a snip however long Ctrl and Cmd rest on the
keys; lists keep their dashes; a sentence keeps the figures that end it;
prices keep their currency; answers out of step are not drawn; the
engine tag is named; a snip's reading goes before background reading."""
import os
import sys
import threading
import time
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import hotkey, identifiers, numbering, overlay, translator


class Release(unittest.TestCase):
    def manager(self):
        m = hotkey.PynputHotkeyManager.__new__(hotkey.PynputHotkeyManager)
        m.reports_release = False
        m._pressed_at, m._released_at = {}, {}
        return m

    def test_unknown_without_release_reports(self):
        m = self.manager()
        m._pressed_at[1] = time.monotonic()
        self.assertIsNone(m.released(1))

    def test_tap_and_hold(self):
        m = self.manager()
        m.reports_release = True
        m._pressed_at[1] = time.monotonic()
        self.assertFalse(m.released(1))            # still held
        m._released_at[1] = time.monotonic()
        self.assertTrue(m.released(1))             # let go: a tap
        m._pressed_at[1] = time.monotonic() + 1    # pressed again
        self.assertFalse(m.released(1))

    def test_carbon_listens_for_release(self):
        from app import hotkey_carbon, hotkey_listener
        self.assertEqual(hotkey_carbon.K_EVENT_HOTKEY_RELEASED, 6)
        with open(hotkey_listener.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("on_release=report_up", src)
        self.assertIn('"RELEASES', src)

    def test_main_decides_by_release(self):
        from app import main
        with open(main.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("gone = let_go()", src)


class Lists(unittest.TestCase):
    def test_dash_is_a_marker(self):
        marker, rest = numbering.split("- Neue Züge")
        self.assertEqual(marker["kind"], "dash")
        self.assertEqual(rest, "Neue Züge")
        self.assertEqual(numbering.attach(marker, "New cables", "en"),
                         "- New cables")
        self.assertEqual(numbering.attach(marker, "- New cables", "en"),
                         "- New cables")

    def test_minus_numbers_are_not_markers(self):
        self.assertIsNone(numbering.split("-5 Grad")[0])
        self.assertIsNone(numbering.split("- 2.500€")[0])


class Figures(unittest.TestCase):
    def lines(self, last="2.500-3000€."):
        return [{"text": "Neupreis allein dieser Kurbel lag bei etwa",
                 "box": (20, 100, 900, 30)},
                {"text": last, "box": (20, 136, 160, 30)},
                {"text": "- Laufräder Fulcrum Racing 7",
                 "box": (20, 172, 360, 30)}]

    def test_figures_ending_a_sentence_are_kept_with_it(self):
        lines = self.lines()
        self.assertNotIn(1, overlay.held_back(lines))
        groups, _held = overlay.paragraphs_for(lines)
        self.assertTrue(any(0 in g and 1 in g for g in groups))

    def test_figures_on_their_own_are_still_held(self):
        lines = self.lines()
        lines[0]["text"] = "Neupreis allein dieser Kurbel."
        self.assertIn(1, overlay.held_back(lines))
        lines = self.lines("12.04.2026")         # no full stop: a value
        self.assertIn(1, overlay.held_back(lines))


class Currency(unittest.TestCase):
    def test_sign_put_back(self):
        self.assertEqual(identifiers.repair(
            "lag bei etwa 2.500-3000€.", "was around 2.500-3000.")[0],
            "was around 2.500-3000€.")
        self.assertEqual(identifiers.repair(
            "nur $49 heute", "only 49 today")[0], "only $49 today")

    def test_left_alone_when_there_or_in_words(self):
        for src, out in (("Preis 49€", "Price €49"),
                         ("Preis 49€", "Price 49€"),
                         ("Kosten 1.299 €", "Costs 1,299 euros")):
            self.assertEqual(identifiers.repair(src, out)[0], out)


class OutOfStep(unittest.TestCase):
    def test_shifted_batch_is_caught(self):
        src = ["- Laufräder Fulcrum Racing 7",
               "Kompletter Service durchgeführt inkl.:", "- Neue Mäntel",
               "- Neue Züge", "- Neues Lenkerband",
               "- Sämtliche Lager gechecked, wo nötig (2x Laufrad) ersetzt, "
               "andere von Dreck befreit und geschmiert."]
        bad = ["- Fulcrum Racing 7 wheels, fully serviced incl. new tires",
               "", "- New cables", "Handlebar tape", "- New handlebar tape",
               "- All bearings checked"]
        good = ["- Fulcrum Racing 7 wheels", "Complete service incl.:",
                "- New tires", "- New cables", "- New handlebar tape",
                "- All bearings checked, replaced where needed (2x wheel), "
                "others cleaned and greased."]
        self.assertTrue(translator._misaligned(src, bad))
        self.assertFalse(translator._misaligned(src, good))

    def test_piece_of_another_line_is_caught(self):
        src = ["Die Kurbel ist fahrbar, aber OHNE POWERMETER-FUNKTION.",
               "- Laufräder Fulcrum Racing 7",
               "Bei Interesse schreib mir gerne!"]
        bad = ["The crank is rideable, but without power-meter function.",
               "- Fulcrum Racing 7 wheels",
               "If interested, message me! OHNE POWERMETER FUNKTION"]
        self.assertTrue(translator._misaligned(src, bad))

    def test_chinese_to_english_is_not_a_shift(self):
        self.assertFalse(translator._misaligned(
            [u"首页", u"新闻", u"联系我们", u"关于"],
            ["Home", "News", "Contact us", "About"]))

    def test_near_copy_is_left_behind(self):
        line = ("- Die hintere Bremse wurde ersetzt durch die CNC gefräste "
                "Fouriers BR-DX001.")
        near = ("- Die hintere Bremse wurde ersetzt durch die CNC-gefräste "
                "Fouriers BR-DX001.")
        self.assertTrue(translator._left_behind(line, near, "en"))
        self.assertFalse(translator._left_behind(
            line, "The rear brake was replaced by the CNC-milled Fouriers "
            "BR-DX001.", "en"))


class EngineTag(unittest.TestCase):
    def test_none_yet_is_not_shown(self):
        old = translator._preferred
        try:
            translator._preferred = None
            self.assertEqual(translator.engine_label(), "")
            self.assertEqual(translator.engine_label("hymt"),
                             "Hy-MT2, on this computer")
        finally:
            translator._preferred = old

    def test_finish_names_the_engine(self):
        from app import main
        with open(main.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("engine=translator.engine_label())", src)
        from app.ui_result import OverlayWindow
        self.assertTrue(hasattr(OverlayWindow, "set_engine"))


class VisionGate(unittest.TestCase):
    def test_snip_goes_before_background(self):
        from app import ocr, ocr_vision
        gate = ocr_vision._Gate()
        order = []
        hold = threading.Event()

        def background(name):
            ocr._thread.no_slow = True
            try:
                with gate:
                    order.append(name)
                    if name == "bg1":
                        hold.wait(1.0)
            finally:
                ocr._thread.no_slow = False

        def snip():
            with gate:
                order.append("snip")
        first = threading.Thread(target=background, args=("bg1",))
        first.start()
        time.sleep(0.05)
        second = threading.Thread(target=background, args=("bg2",))
        second.start()
        time.sleep(0.05)
        third = threading.Thread(target=snip)
        third.start()
        time.sleep(0.05)
        hold.set()
        for t in (first, second, third):
            t.join(3)
        self.assertEqual(order, ["bg1", "snip", "bg2"])


class FailureLog(unittest.TestCase):
    def test_same_failure_logged_once(self):
        from app import preread
        said = []
        old = preread._log
        preread._log = said.append
        preread._failures.clear()
        try:
            for _ in range(5):
                try:
                    raise RuntimeError("no screen")
                except RuntimeError:
                    preread._log_failure()
        finally:
            preread._log = old
        self.assertEqual(len(said), 1)


if __name__ == "__main__":
    unittest.main()


class Missed(unittest.TestCase):
    """Rows of text the earlier reading has no line on are read again."""

    def page(self):
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (600, 200), "white")
        draw = ImageDraw.Draw(img)
        for i in range(5):
            draw.text((10, 10 + 36 * i), "Zeile %d mit etwas Text darin, "
                      "lang genug" % i, fill="black")
        lines = [{"text": "x", "box": (10, 8 + 36 * i, 300, 16)}
                 for i in range(5)]
        return img, lines

    def test_all_read(self):
        from app import preread
        img, lines = self.page()
        self.assertEqual(preread._unread_bands(img, lines), [])

    def test_missing_line_found(self):
        from app import preread
        img, lines = self.page()
        bands = preread._unread_bands(img, lines[:2] + lines[3:])
        self.assertEqual(len(bands), 1)
        top, bottom = bands[0]
        self.assertTrue(80 <= top <= 90 and bottom <= 100)


class Dots(unittest.TestCase):
    def test_dots_without_space_end_a_sentence(self):
        from app import offline_model as om
        self.assertEqual(len(om._sentences(
            "zu verkaufen....Das Rad wiegt knapp 7Kg...Mehr folgt")), 3)
        self.assertEqual(len(om._sentences("Version 1.2.3 ist da.")), 1)
        self.assertEqual(len(om._sentences("Es kam...ok")), 1)


class SelectionLog(unittest.TestCase):
    def test_reasons_logged_once(self):
        from app import select_icon
        said = []
        w = select_icon.Watcher(None, lambda t, h: None, log=said.append)
        for _ in range(3):
            w.note("not shown (the app reported no selection)")
        w.note("shown")
        w.note("shown")
        self.assertEqual(len(said), 3)
