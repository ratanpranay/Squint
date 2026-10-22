"""The offline translator is fetched on the first start without being
asked, and left alone by anyone who switched it off or removed it."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config, offline_model as om  # noqa: E402


class AutoSetup(unittest.TestCase):
    def setUp(self):
        self.cfg = {}
        self.started = []
        patches = [
            mock.patch.dict(config.CONFIG, {}, clear=False),
            mock.patch.object(config.Config, "save", lambda self: None),
            mock.patch.object(om, "start_download",
                              lambda which, on_progress=None, on_done=None:
                              self.started.append((which, on_done)) or True),
            mock.patch.object(om, "installed", lambda which=None: None),
            mock.patch.object(om, "engine_path", lambda: None),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        for key in ("offline_declined", "offline_paused", "offline_auto_done",
                    "offline_enabled"):
            config.CONFIG.pop(key, None)
        om._download["thread"] = None

    def test_first_start_downloads_and_switches_on(self):
        self.assertEqual(om.auto_setup(), "downloading")
        self.assertEqual(len(self.started), 1)
        self.assertTrue(config.CONFIG.get("offline_enabled"))

    def test_resumes_on_the_next_start(self):
        om.auto_setup()
        self.assertEqual(om.auto_setup(), "downloading")
        self.assertEqual(len(self.started), 2)

    def test_switched_off_is_left_alone(self):
        config.CONFIG["offline_declined"] = True
        self.assertEqual(om.auto_setup(), "declined")
        self.assertEqual(self.started, [])

    def test_paused_is_left_alone(self):
        config.CONFIG["offline_paused"] = True
        self.assertEqual(om.auto_setup(), "paused")
        self.assertEqual(self.started, [])

    def test_off_after_it_was_set_up_is_left_alone(self):
        config.CONFIG["offline_auto_done"] = True
        config.CONFIG["offline_enabled"] = False
        self.assertEqual(om.auto_setup(), "switched off")
        self.assertEqual(self.started, [])

    def test_model_already_here(self):
        with mock.patch.object(om, "installed", lambda which=None: "standard"), \
                mock.patch.object(om, "engine_path", lambda: "/x/llama-server"):
            self.assertEqual(om.auto_setup(), "present")
        self.assertEqual(self.started, [])

    def test_no_room(self):
        class Usage:
            free = 1024 ** 3
        with mock.patch("shutil.disk_usage", lambda p: Usage()):
            self.assertEqual(om.auto_setup(), "not enough disk space")
        self.assertEqual(self.started, [])
        self.assertFalse(config.CONFIG.get("offline_enabled"))

    def test_tested_when_it_arrives(self):
        om.auto_setup()
        _which, done = self.started[0]
        with mock.patch.object(om, "self_test",
                               return_value=(True, "works")) as test:
            done("ready", "")
        test.assert_called_once()


if __name__ == "__main__":
    unittest.main()
