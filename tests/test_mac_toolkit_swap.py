"""The Mac app's Tk 9 crashed when screens changed; an update swaps in
Tk 8.6 beside it, checks it, and undoes anything short of a success."""
import io
import os
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config, mac_toolkit as mt  # noqa: E402


def archive(with_tk86=True):
    """with_tk86: an older build, Tk 8.6 linked into _tkinter, with only its
    script folders (no libtk8.6.dylib). Otherwise a Tk 9 build."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        files = {"python/" + mt.TKINTER: b"tk86-module",
                 "python/bin/python3": b"not wanted"}
        if with_tk86:
            files["python/lib/tcl8.6/init.tcl"] = b"init"
            files["python/lib/tk8.6/tk.tcl"] = b"tk"
        else:
            files["python/lib/libtcl9tk9.0.dylib"] = b"tk9"
            files["python/lib/tcl9.0/init.tcl"] = b"init9"
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    buf.seek(0)
    return buf


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class SwapTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.root = os.path.join(self.dir, "venv")
        os.makedirs(os.path.dirname(os.path.join(self.root, mt.TKINTER)))
        with open(os.path.join(self.root, mt.TKINTER), "wb") as fh:
            fh.write(b"tk9-module")
        config.CONFIG.save = lambda: None
        self.patches = [
            mock.patch.object(mt, "venv_root", lambda: self.root),
            mock.patch.object(config, "data_dir", lambda: self.dir),
            mock.patch.object(mt, "_asset", lambda tag: "https://x/" + tag),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        # Removed, not put back: a bound method left on the instance
        # would hide every later patch of Config.save, and tests after
        # this one wrote their made-up settings to the real config file.
        config.CONFIG.__dict__.pop("save", None)

    def read(self, rel):
        with open(os.path.join(self.root, rel), "rb") as fh:
            return fh.read()

    def test_tk86_is_put_in_and_tk9_kept_as_a_backup(self):
        with mock.patch.object(mt, "_open", lambda url, timeout=0: Reply(
                archive().read())), \
                mock.patch.object(mt, "_works", lambda root: True):
            ok, _ = mt.swap()
        self.assertTrue(ok)
        self.assertEqual(self.read(mt.TKINTER), b"tk86-module")
        self.assertEqual(self.read(mt.TKINTER + ".tk9"), b"tk9-module")
        self.assertTrue(os.path.exists(
            os.path.join(self.root, "lib", "tcl8.6", "init.tcl")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "bin")))
        self.assertTrue(mt.already_swapped(self.root))

    def test_a_release_without_tk86_is_passed_over(self):
        replies = iter([archive(False).read(), archive(True).read()])
        with mock.patch.object(mt, "_open", lambda url, timeout=0: Reply(
                next(replies))), \
                mock.patch.object(mt, "_works", lambda root: True):
            ok, _ = mt.swap()
        self.assertTrue(ok)

    def test_one_that_does_not_load_is_undone(self):
        with mock.patch.object(mt, "_open", lambda url, timeout=0: Reply(
                archive().read())), \
                mock.patch.object(mt, "_works", lambda root: False):
            ok, _ = mt.swap()
        self.assertFalse(ok)
        self.assertEqual(self.read(mt.TKINTER), b"tk9-module")
        self.assertFalse(mt.already_swapped(self.root))

    def test_nothing_found_changes_nothing(self):
        def fail(url, timeout=0):
            raise OSError("offline")
        with mock.patch.object(mt, "_open", fail):
            ok, message = mt.swap()
        self.assertFalse(ok)
        self.assertEqual(self.read(mt.TKINTER), b"tk9-module")


class CrashTests(SwapTests):
    def swapped(self):
        with mock.patch.object(mt, "_open", lambda url, timeout=0: Reply(
                archive().read())), \
                mock.patch.object(mt, "_works", lambda root: True):
            self.assertTrue(mt.swap()[0])

    def test_toolkit_crash_puts_tk9_back_and_stops(self):
        self.swapped()
        config.CONFIG["tk86_swap_failed"] = False
        self.assertTrue(mt.undo_after_crash(
            'File "PIL/ImageTk.py"\nTypeError: bad argument type'))
        self.assertEqual(self.read(mt.TKINTER), b"tk9-module")
        self.assertTrue(config.CONFIG.get("tk86_swap_failed"))
        self.assertFalse(mt.undo_after_crash("_tkinter"))

    def test_unrelated_crash_leaves_it(self):
        self.swapped()
        self.assertFalse(mt.undo_after_crash("KeyError: 'x' in translator"))
        self.assertEqual(self.read(mt.TKINTER), b"tk86-module")


class WhenTests(unittest.TestCase):
    def test_only_the_mac_app(self):
        with mock.patch.object(mt.sys, "platform", "win32"):
            self.assertIsNone(mt.venv_root())
        with mock.patch.object(mt.sys, "platform", "darwin"), \
                mock.patch.object(mt.sys, "prefix", "/usr/local"):
            self.assertIsNone(mt.venv_root())

    def test_not_when_tk_is_already_86(self):
        with mock.patch.object(mt, "venv_root", lambda: "/x"), \
                mock.patch.object(mt, "current_tk", lambda: 8.6):
            self.assertFalse(mt.needed())


if __name__ == "__main__":
    unittest.main()
