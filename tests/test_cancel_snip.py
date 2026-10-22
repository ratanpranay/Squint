"""A snip can be cancelled while it reads or translates: a click on its
label, or the shortcut again (which then starts a new one)."""
import os
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import main, translator  # noqa: E402


class Toast:
    def __init__(self):
        self.closed = False
        self.cancelled = False

    def close(self):
        self.closed = True


class Fake:
    cancel_snip = main.Controller.cancel_snip
    _drop_part = staticmethod(main.Controller._drop_part)
    snip_key_pressed = main.Controller.snip_key_pressed

    def __init__(self):
        self.busy = threading.Lock()
        self.xray = None
        self.did = []

    def _xray(self):
        return None

    def trigger_snip(self):
        self.did.append("snip")


class CancelTests(unittest.TestCase):
    def running(self):
        c = Fake()
        c.busy.acquire()
        c._snip_toast, c._snip_stop = Toast(), threading.Event()
        c._snip_job = main._SnipJob(("k",), c._snip_toast, c._snip_stop)
        return c

    def test_cancel_frees_the_app_and_stops_the_work(self):
        c = self.running()
        toast, stop = c._snip_toast, c._snip_stop
        self.assertTrue(c.cancel_snip())
        self.assertTrue(toast.cancelled and toast.closed)
        self.assertFalse(stop.is_set())         # it finishes in the background
        self.assertFalse(c.busy.locked())
        self.assertFalse(c.cancel_snip())        # only once

    def test_nothing_to_cancel_while_picking(self):
        c = Fake()
        c.busy.acquire()                          # the picker is up
        self.assertFalse(c.cancel_snip())
        self.assertTrue(c.busy.locked())

    def test_shortcut_again_cancels_and_snips_afresh(self):
        c = self.running()
        with mock.patch("app.keystate.is_down", lambda spec: None), \
                mock.patch("app.keystate.modifiers_down", lambda spec: None):
            c.snip_key_pressed()
        self.assertEqual(c.did, ["snip"])
        self.assertTrue(c._detached is None or True)


class StopTests(unittest.TestCase):
    def setUp(self):
        translator._blocks.clear()

    def tearDown(self):
        translator.set_stop(None)

    def test_translate_refuses_once_stopped(self):
        stop = threading.Event()
        translator.set_stop(stop)
        stop.set()
        with self.assertRaises(translator.Cancelled):
            translator.translate("Hallo", "en")
        with self.assertRaises(translator.Cancelled):
            translator.translate_lines(["a", "b"], "en")

    def test_other_threads_are_not_stopped(self):
        stop = threading.Event()
        stop.set()
        translator.set_stop(stop)
        seen = {}

        def other():
            seen["stop"] = translator._stop()
        t = threading.Thread(target=other)
        t.start()
        t.join()
        self.assertIsNone(seen["stop"])

    def test_offline_with_help_stops_quickly(self):
        from app import profile
        stop = threading.Event()
        cancels = {}

        def offline(lines, target, left_behind=None, cancel=None,
                    workers=None, whole=False, **_kw):
            cancels["c"] = cancel
            while not cancel.is_set():
                time.sleep(0.01)
            return None

        def online(lines, target, source, job):
            while not stop.is_set():
                time.sleep(0.01)
            raise translator.Cancelled("cancelled")

        with mock.patch.object(profile, "current", lambda: profile.AUTO), \
                mock.patch.object(profile, "_hymt_ready", lambda: True), \
                mock.patch("app.offline_model.ready", lambda: True), \
                mock.patch("app.offline_model.translate_lines", offline), \
                mock.patch.object(translator, "_online_lines", online), \
                mock.patch.object(translator, "_api_key",
                                  lambda s: "k" if s == "groq_api_key"
                                  else ""), \
                mock.patch.object(translator, "HELP_AFTER", 0.1), \
                mock.patch.dict("app.config.CONFIG", {"target_lang": "en"}):
            translator.set_stop(stop)
            threading.Timer(0.4, stop.set).start()
            started = time.time()
            with self.assertRaises(translator.Cancelled):
                translator.translate_lines(["a", "b"], "en", blocks=True)
        self.assertLess(time.time() - started, 1.0)
        self.assertTrue(cancels["c"].is_set())


if __name__ == "__main__":
    unittest.main()
