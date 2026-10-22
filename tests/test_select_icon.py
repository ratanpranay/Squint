"""The Squint icon beside selected text: when it appears, when it does
not, and what a click on it does."""
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import select_icon

try:
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
except Exception:                     # pragma: no cover
    root = None


class Mouse:
    def __init__(self):
        self.down = False
        self.at = (500, 400)
        self.text = True


@unittest.skipIf(root is None, "no display")
class Icon(unittest.TestCase):
    def watcher(self, mac_text=None, front=4242, **kw):
        self.mouse = Mouse()
        self.clicked = []
        args = dict(pressed=lambda: self.mouse.down,
                    pointer=lambda: self.mouse.at,
                    front=lambda: front,
                    is_text=lambda: self.mouse.text)
        if mac_text is not None:
            args["read_text"] = lambda handle: mac_text
        args.update(kw)
        w = select_icon.Watcher(root, lambda t, h: self.clicked.append((t, h)),
                                **args)
        w.over_squint = lambda x, y: False
        w._was_down = False
        self.addCleanup(lambda: (w.stop(), w.icon and w.icon.destroy()))
        return w

    def step(self, w, n=1):
        for _ in range(n):
            w._step()
            root.update()

    def drag(self, w, start=(500, 400), end=(640, 420)):
        self.mouse.at = start
        self.mouse.down = True
        self.step(w)
        self.mouse.at = end
        self.step(w)
        self.mouse.down = False
        self.step(w)

    def click(self, w, at):
        self.mouse.at = at
        self.mouse.down = True
        self.step(w)
        self.mouse.down = False
        self.step(w)

    def wait_answer(self, w):
        for _ in range(50):
            self.step(w)
            if w._offer is not None:
                return
            time.sleep(0.01)

    def shown(self, w):
        return w._offer is not None and w.icon is not None and \
            w.icon.box() is not None

    def test_drag_over_text_shows_icon_near_the_end(self):
        w = self.watcher()
        self.drag(w)
        self.assertTrue(self.shown(w))
        x0, y0, _x1, _y1 = w.icon.box()
        self.assertGreater(x0, 640)
        self.assertGreater(y0, 420)

    def test_click_on_icon_translates(self):
        w = self.watcher()
        self.drag(w)
        w._clicked()
        self.assertEqual(self.clicked, [(None, 4242)])
        self.assertFalse(self.shown(w))

    def test_drag_with_the_arrow_is_not_text(self):
        w = self.watcher()
        self.mouse.text = False
        self.drag(w)
        self.assertFalse(self.shown(w))

    def test_single_click_is_not_a_selection(self):
        w = self.watcher()
        self.click(w, (500, 400))
        self.assertFalse(self.shown(w))

    def test_double_click_selects_a_word(self):
        w = self.watcher()
        self.click(w, (500, 400))
        self.click(w, (501, 400))
        self.assertTrue(self.shown(w))

    def test_two_clicks_far_apart_are_not_a_double_click(self):
        w = self.watcher()
        self.click(w, (500, 400))
        self.click(w, (700, 300))
        self.assertFalse(self.shown(w))

    def test_click_elsewhere_dismisses(self):
        w = self.watcher()
        self.drag(w)
        self.click(w, (100, 100))
        self.assertFalse(self.shown(w))

    def test_press_on_the_icon_does_not_dismiss(self):
        w = self.watcher()
        self.drag(w)
        x0, y0, x1, y1 = w.icon.box()
        self.mouse.at = ((x0 + x1) // 2, (y0 + y1) // 2)
        self.mouse.down = True
        self.step(w)
        self.assertTrue(self.shown(w))

    def test_goes_by_itself(self):
        w = self.watcher()
        self.drag(w)
        self.mouse.at = (10, 10)
        w._shown_at -= select_icon.SHOW_FOR + 1
        self.step(w)
        self.assertFalse(self.shown(w))

    def test_not_over_squint_not_while_busy_not_for_the_taskbar(self):
        w = self.watcher()
        w.over_squint = lambda x, y: True
        self.drag(w)
        self.assertFalse(self.shown(w))
        w = self.watcher(blocked=lambda: True)
        self.drag(w)
        self.assertFalse(self.shown(w))
        w = self.watcher(front=None)
        self.drag(w)
        self.assertFalse(self.shown(w))

    def test_mac_asks_for_the_text_and_hands_it_over(self):
        w = self.watcher(mac_text=u"Mit „Sicher bezahlen“ gilt der Käuferschutz.")
        self.drag(w)
        self.wait_answer(w)
        self.assertTrue(self.shown(w))
        w._clicked()
        self.assertEqual(self.clicked[0][0],
                         u"Mit „Sicher bezahlen“ gilt der Käuferschutz.")

    def test_mac_no_selected_text_no_icon(self):
        w = self.watcher(mac_text="   ")
        self.drag(w)
        for _ in range(10):
            self.step(w)
            time.sleep(0.01)
        self.assertFalse(self.shown(w))

    def test_app_that_will_not_say_still_gets_the_icon(self):
        w = self.watcher(mac_text=True)
        self.drag(w)
        self.wait_answer(w)
        self.assertTrue(self.shown(w))
        w._clicked()
        self.assertEqual(self.clicked, [(None, 4242)])

    def test_icon_is_the_logo(self):
        w = self.watcher()
        self.drag(w)
        self.assertIsNotNone(w.icon.photo)

    def test_stop_hides_and_stops(self):
        w = self.watcher()
        w.start()
        self.drag(w)
        w.stop()
        self.assertFalse(self.shown(w))
        self.assertFalse(w._running)


class Gesture(unittest.TestCase):
    def test_drag_and_clicks(self):
        self.assertTrue(select_icon.is_gesture((0, 0, 0), (0.3, 20, 0),
                                               None, 1))
        self.assertFalse(select_icon.is_gesture((0, 0, 0), (0.1, 2, 1),
                                                None, 1))
        self.assertTrue(select_icon.is_gesture((0, 0, 0), (0.1, 2, 1),
                                               None, 2))

    def test_off_platform_readers_are_quiet(self):
        if sys.platform in ("darwin", "win32"):
            self.skipTest("real platform")
        self.assertEqual(select_icon.mac_selected_text(1), "")
        self.assertFalse(select_icon.windows_cursor_is_text())

    def test_logo_is_found(self):
        self.assertTrue(select_icon._logo_path())


class Wiring(unittest.TestCase):
    def test_app_uses_the_given_text(self):
        from app import main
        with open(main.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("def trigger_clipboard(self, given=None)", src)
        self.assertIn("content = given or selection.grab", src)
        self.assertIn("self._start_select_icon()", src)
        from app.config import DEFAULTS
        self.assertTrue(DEFAULTS.get("select_icon"))


if __name__ == "__main__":
    unittest.main()
