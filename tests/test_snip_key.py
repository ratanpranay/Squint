"""One shortcut: tap to snip, hold to see translated, letter twice to keep."""
import os
import sys
import threading
import time
import tkinter
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import keystate, main  # noqa: E402


class Fake:
    HOLD_SECONDS = main.Controller.HOLD_SECONDS
    HOLD_LONG = main.Controller.HOLD_LONG
    HOLD_POLL_MS = main.Controller.HOLD_POLL_MS
    snip_key_pressed = main.Controller.snip_key_pressed
    cancel_snip = main.Controller.cancel_snip

    def __init__(self, root):
        self.root = root
        self.busy = threading.Lock()
        self.xray = None
        self.did = []

    def _xray(self):
        return self.xray

    def trigger_snip(self):
        self.did.append("snip")

    def trigger_xray(self):
        self.did.append("xray")


class SnipKeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tkinter.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def run_for(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.root.update()

    def press(self, release_after, mods_after=None, wait=0.6):
        c = Fake(self.root)
        t0 = time.time()
        mods_after = release_after if mods_after is None else mods_after
        with mock.patch.object(keystate, "is_down",
                               lambda spec: time.time() - t0 < release_after), \
                mock.patch.object(keystate, "modifiers_down",
                                  lambda spec: time.time() - t0 < mods_after):
            c.snip_key_pressed()
            self.run_for(wait)
        return c.did

    def test_tap_with_slow_modifiers_still_snips(self):
        self.assertEqual(self.press(0.08, mods_after=0.5, wait=0.8),
                         ["snip"])

    def test_x_let_go_with_ctrl_alt_still_held_is_a_snip(self):
        self.assertEqual(self.press(0.1, mods_after=5, wait=0.6), ["snip"])

    def test_x_unreadable_from_the_start_with_ctrl_alt_held_is_a_hold(self):
        # First press on a new page: X read as up while held.
        self.assertEqual(self.press(0.0, mods_after=5, wait=0.6), ["xray"])

    def test_one_stray_up_reading_is_not_a_tap(self):
        c = Fake(self.root)
        t0 = time.time()
        reads = {"n": 0}

        def is_down(spec):
            reads["n"] += 1
            return reads["n"] != 2           # a single stray "up"
        with mock.patch.object(keystate, "is_down", is_down), \
                mock.patch.object(keystate, "modifiers_down",
                                  lambda spec: True):
            c.snip_key_pressed()
            self.run_for(0.6)
        self.assertEqual(c.did, ["xray"])

    def test_tap_snips(self):
        self.assertEqual(self.press(0.08), ["snip"])

    def test_hold_shows_translated(self):
        self.assertEqual(self.press(5), ["xray"])

    def test_unknown_key_state_snips_as_before(self):
        c = Fake(self.root)
        with mock.patch.object(keystate, "is_down", lambda spec: None):
            c.snip_key_pressed()
        self.assertEqual(c.did, ["snip"])

    def test_press_while_view_is_up_goes_to_it(self):
        c = Fake(self.root)
        view = mock.Mock(win=object(), opening=False)
        c.xray = view
        c.snip_key_pressed()
        view.press.assert_called_once()
        self.assertEqual(c.did, [])


if __name__ == "__main__":
    unittest.main()
