"""Automatic: one engine per page, chosen before anything is sent - the
offline model, unless its recent speed says the page would take it past
three seconds; then Groq/Gemini. One failing hands the page to the other.
Never a race between them."""
import os
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import profile, translator  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch.object(profile, "current", lambda: profile.AUTO),
            mock.patch.object(profile, "_hymt_ready", lambda: True),
            mock.patch("app.offline_model.ready", lambda: True),
            mock.patch.object(translator, "_api_key",
                              lambda s: "k" if s == "groq_api_key" else ""),
            mock.patch.object(translator, "HELP_AFTER", 0.2),
            mock.patch.dict("app.config.CONFIG", {"target_lang": "en"}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        translator._hymt_speed["per_item"] = None
        translator._hymt_speed["per_char"] = None
        translator._speed_seen[:] = []
        translator._cooldown.clear()


class OrderTests(Base):
    def test_offline_leads_then_groq_then_gemini(self):
        order, fallback = profile.translating(profile.SPEED)
        self.assertEqual(order[:3], ["hymt", "groq", "gemini"])
        self.assertTrue(fallback)

    def test_not_run_beside_when_it_leads(self):
        self.assertIsNone(translator._hymt_beside(["a"], "en", None))


class HelpTests(Base):
    def run_page(self, offline_delay, online_delay, lines=("a", "b")):
        stop = {}

        def offline(lines, target, left_behind=None, cancel=None,
                    workers=None, whole=False, **_kw):
            stop["cancel"] = cancel
            end = time.time() + offline_delay
            while time.time() < end:
                if cancel is not None and cancel.is_set():
                    return None
                time.sleep(0.01)
            return ["off " + l for l in lines]

        def online(lines, target, source, job):
            time.sleep(online_delay)
            return ["on " + l for l in lines]

        with mock.patch("app.offline_model.translate_lines", offline), \
                mock.patch.object(translator, "_online_lines", online), \
                mock.patch.object(translator, "_cache_get", lambda k: None), \
                mock.patch.object(translator, "_cache_put",
                                  lambda k, v: None):
            return translator._hymt_with_help(list(lines), "en", "auto",
                                              None, whole=True), stop

    def test_fast_offline_needs_no_help(self):
        with mock.patch.object(translator, "_online_lines",
                               side_effect=AssertionError("asked")):
            out, _ = self.run_page(0.05, 5)
        self.assertEqual(out, ["off a", "off b"])

    def test_slow_offline_is_not_raced(self):
        # Speed not yet known: the offline model translates, however long
        # it takes, and nothing else is asked beside it.
        with mock.patch.object(translator, "_online_lines",
                               side_effect=AssertionError("raced")):
            out, _ = self.run_page(0.6, 0.1)
        self.assertEqual(out, ["off a", "off b"])

    def test_offline_failing_goes_online(self):
        def broken(*a, **k):
            raise RuntimeError("no model")
        with mock.patch("app.offline_model.translate_lines", broken), \
                mock.patch.object(translator, "_online_lines",
                                  lambda l, t, s, j: ["on " + x for x in l]), \
                mock.patch.object(translator, "_cache_get", lambda k: None):
            out = translator._hymt_with_help(["a", "b"], "en", "auto", None,
                                             whole=True)
        self.assertEqual(out, ["on a", "on b"])

    def test_speed_is_learned_from_offline(self):
        from app import offline_model
        long_lines = ("x" * 100, "y" * 100)
        with mock.patch.dict(offline_model.last_run, {"work": 0.4,
                                                       "load": 6.6}):
            self.run_page(0.2, 5, long_lines)
        self.assertAlmostEqual(translator._hymt_speed["per_char"],
                               0.4 / 200, places=6)

    def test_model_start_and_tiny_pages_are_not_learned(self):
        from app import offline_model
        with mock.patch.dict(offline_model.last_run, {"work": 0.2,
                                                       "load": 6.6}):
            self.run_page(0.2, 5, ("Hallo",))
        self.assertIsNone(translator._hymt_speed["per_char"])

    def test_gemini_alone_is_not_chosen_for_speed(self):
        translator._hymt_speed["per_char"] = 5.0
        with mock.patch.object(translator, "_api_key",
                               lambda s: "k" if s == "gemini_api_key"
                               else ""), \
                mock.patch.object(translator, "_online_lines",
                                  side_effect=AssertionError("online")):
            out, _ = self.run_page(0.1, 0.05)
        self.assertEqual(out, ["off a", "off b"])

    def test_no_helper_key_is_not_this_route(self):
        with mock.patch.object(translator, "_api_key", lambda s: ""):
            out, _ = self.run_page(0.05, 0.05)
        self.assertIsNone(out)

    def test_helper_out_of_quota_is_not_asked(self):
        translator._cooldown["groq"] = (time.monotonic() + 60, "quota")
        out, _ = self.run_page(0.05, 0.05)
        self.assertIsNone(out)

    def test_known_slow_offline_sends_the_page_online_at_once(self):
        translator._hymt_speed["per_char"] = 5.0     # 2 chars: 10 s
        started = time.time()
        with mock.patch("app.offline_model.translate_lines",
                        side_effect=AssertionError("offline asked")):
            out, _ = self.run_page(3.0, 0.05)
        self.assertEqual(out, ["on a", "on b"])
        self.assertLess(time.time() - started, 0.5)

    def test_known_fast_offline_is_kept(self):
        translator._hymt_speed["per_char"] = 0.01
        with mock.patch.object(translator, "_online_lines",
                               side_effect=AssertionError("asked")):
            out, _ = self.run_page(0.1, 0.05)
        self.assertEqual(out, ["off a", "off b"])


class DensePageTests(HelpTests):
    """A full page on a computer without a usable graphics chip asks for
    help at once, before the offline engine's speed is known."""
    PAGE = tuple("line %d" % i for i in range(40))

    def timed(self, gpu, lines):
        started = time.time()
        with mock.patch("app.offline_model.on_graphics_chip", lambda: gpu):
            out, _ = self.run_page(0.3, 0.05, lines)
        return out, time.time() - started

    def test_dense_page_on_processor_goes_online(self):
        out, took = self.timed(False, self.PAGE)
        self.assertTrue(out[0].startswith("on "))
        self.assertLess(took, 0.5)

    def test_dense_page_on_graphics_chip_stays_offline(self):
        out, took = self.timed(True, self.PAGE)
        self.assertTrue(out[0].startswith("off "))

    def test_short_snip_on_processor_stays_offline(self):
        out, took = self.timed(False, ("a", "b"))
        self.assertTrue(out[0].startswith("off "))

    # Inherited race tests do not apply to a full page.
    def test_slow_offline_is_not_raced(self):
        pass

    def test_known_slow_offline_sends_the_page_online_at_once(self):
        pass

    def test_offline_failing_goes_online(self):
        pass

    def test_speed_is_learned_from_offline(self):
        pass

    def test_model_start_and_tiny_pages_are_not_learned(self):
        pass

    def test_gemini_alone_is_not_chosen_for_speed(self):
        pass

    def test_known_fast_offline_is_kept(self):
        pass

    def test_fast_offline_needs_no_help(self):
        pass

    def test_offline_still_wins_if_it_finishes_first(self):
        pass


if __name__ == "__main__":
    unittest.main()
