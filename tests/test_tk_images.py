"""Pillow's Tk bridge cannot attach to the Mac app's built-in Tk 8.6; the
pictures must still reach Tk, as PNG data."""
import os
import sys
import tkinter
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageTk  # noqa: E402
from app import tk_images  # noqa: E402


class FallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tkinter.Tk()
        cls.root.withdraw()
        tk_images.install()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        tk_images._state["fallback"] = False

    def check(self, mode, colour, want):
        img = Image.new(mode, (7, 5), colour)
        photo = ImageTk.PhotoImage(img, master=self.root)
        self.assertEqual((photo.width(), photo.height()), (7, 5))
        got = self.root.tk.call(str(photo), "get", 3, 2)
        if isinstance(got, str):
            got = tuple(int(x) for x in got.split())
        self.assertEqual(tuple(got)[:3], want)

    def test_fast_path_still_used_when_it_works(self):
        self.check("RGB", (10, 200, 30), (10, 200, 30))
        self.assertFalse(tk_images._state["fallback"])

    def test_broken_bridge_falls_back_to_png(self):
        def broken(*a):
            raise TypeError("bad argument type for built-in operation")
        with mock.patch("PIL.ImageTk._pyimagingtkcall", broken):
            self.check("RGB", (10, 200, 30), (10, 200, 30))
            self.assertTrue(tk_images._state["fallback"])
            self.check("RGBA", (250, 5, 60, 255), (250, 5, 60))
            self.check("L", 128, (128, 128, 128))
            self.check("P", 0, (0, 0, 0))

    def test_install_twice_wraps_once(self):
        paste = ImageTk.PhotoImage.paste
        tk_images.install()
        self.assertIs(ImageTk.PhotoImage.paste, paste)


if __name__ == "__main__":
    unittest.main()
