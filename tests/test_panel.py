"""The small panel the menu-bar and tray icon open: where it goes, what
its buttons do, and that the icon still has its menu."""
import os
import sys
import time
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import ui_panel

try:
    import tkinter as tk
    from app import theme
    root = tk.Tk()
    root.withdraw()
except Exception:                     # pragma: no cover
    root = None

SCREEN = (0, 0, 1920, 1080)


class Place(unittest.TestCase):
    def test_under_the_icon(self):
        x, y = ui_panel.place(300, 180, (0, 0), SCREEN,
                              anchor=(1500, 0, 1530, 24))
        self.assertEqual(y, 30)
        self.assertEqual(x, 1515 - 150)

    def test_icon_at_the_right_edge_stays_on_screen(self):
        x, _y = ui_panel.place(300, 180, (0, 0), SCREEN,
                               anchor=(1890, 0, 1915, 24))
        self.assertLessEqual(x + 300, 1920)

    def test_taskbar_at_the_bottom_opens_above(self):
        x, y = ui_panel.place(300, 180, (1800, 1060), SCREEN,
                              work=(0, 0, 1920, 1032))
        self.assertLessEqual(y + 180, 1032)
        self.assertLessEqual(x + 300, 1920)

    def test_taskbar_at_the_top_opens_below(self):
        _x, y = ui_panel.place(300, 180, (900, 20), SCREEN,
                               work=(0, 48, 1920, 1080))
        self.assertGreaterEqual(y, 48)


class Status(unittest.TestCase):
    def line(self, state, ready, enabled=True):
        with mock.patch("app.offline_model.download_state",
                        return_value=state), \
                mock.patch("app.offline_model.ready", return_value=ready):
            return ui_panel.status_line({"offline_enabled": enabled})

    def test_ready(self):
        self.assertEqual(self.line({"state": "ready"}, True),
                         ("Offline ready", "success"))

    def test_downloading_shows_progress(self):
        text, colour = self.line(
            {"state": "downloading", "done": 42, "total": 100}, False)
        self.assertIn("42%", text)
        self.assertEqual(colour, "warning")

    def test_online(self):
        self.assertEqual(self.line({"state": "idle"}, False, False)[0],
                         "Online translation")


@unittest.skipIf(root is None, "no display")
class Panel(unittest.TestCase):
    def setUp(self):
        self.calls = []
        ui_panel.MiniPanel._closed_at = 0.0

    def open(self, **kw):
        args = dict(on_snip=lambda: self.calls.append("snip"),
                    on_text=lambda: self.calls.append("text"),
                    on_language=lambda c: self.calls.append(("lang", c)),
                    on_settings=lambda: self.calls.append("settings"),
                    language="en", keys=("Ctrl+Alt+X", "Ctrl+Alt+C"),
                    status=lambda: ("Offline ready", "success"))
        args.update(kw)
        panel = ui_panel.MiniPanel.toggle(root, theme.resolve("light"),
                                          **args)
        root.update()
        self.addCleanup(lambda: (panel and panel.close(), root.update()))
        return panel

    def wait(self, ms=200):
        end = time.monotonic() + ms / 1000.0
        while time.monotonic() < end:
            root.update()
            time.sleep(0.01)

    def text_of(self, panel):
        c = panel.canvas
        return [c.itemcget(i, "text") for i in c.find_all()
                if c.type(i) == "text"]

    def test_shows_buttons_keys_language_and_status(self):
        panel = self.open()
        texts = self.text_of(panel)
        for want in ("Snip", "Text", "Ctrl+Alt+X", "Ctrl+Alt+C", "English",
                     "Offline ready"):
            self.assertIn(want, texts)
        self.assertEqual(panel.winfo_width(), panel.width)

    def test_snip_closes_first_then_snips(self):
        panel = self.open()
        panel._do("snip")
        self.assertFalse(ui_panel.MiniPanel.is_open())
        self.assertEqual(self.calls, [])
        self.wait(250)
        self.assertEqual(self.calls, ["snip"])

    def test_text_and_settings(self):
        self.open()._do("text")
        ui_panel.MiniPanel._closed_at = 0.0
        self.open()._do("settings")
        self.wait(250)
        self.assertEqual(sorted(self.calls), ["settings", "text"])

    def test_language_changes_and_shows(self):
        panel = self.open()
        panel.choose("de")
        self.assertIn(("lang", "de"), self.calls)
        self.assertIn("German", self.text_of(panel))
        self.assertTrue(ui_panel.MiniPanel.is_open())

    def test_status_follows_download(self):
        state = {"line": ("Getting offline model… 10%", "warning")}
        panel = self.open(status=lambda: state["line"])
        state["line"] = ("Offline ready", "success")
        panel._tick()
        self.assertIn("Offline ready", self.text_of(panel))

    def test_icon_click_toggles(self):
        panel = self.open()
        self.assertIsNotNone(panel)
        again = ui_panel.MiniPanel.toggle(root, theme.resolve("light"))
        self.assertIsNone(again)
        self.assertFalse(ui_panel.MiniPanel.is_open())

    def test_click_that_closed_it_does_not_reopen(self):
        panel = self.open()
        panel.close()
        self.assertIsNone(ui_panel.MiniPanel.toggle(
            root, theme.resolve("light")))
        ui_panel.MiniPanel._closed_at = 0.0
        self.assertIsNotNone(self.open())

    def test_dark_and_status_errors(self):
        def broken():
            raise RuntimeError("no")
        panel = ui_panel.MiniPanel(
            root, theme.resolve("dark"), on_snip=None, on_text=None,
            on_language=None, on_settings=None, status=broken)
        self.addCleanup(panel.close)
        root.update()
        self.assertTrue(panel.winfo_exists())

    def test_hover(self):
        panel = self.open()
        panel._hover_on("snip")
        panel._hover_on("gear")
        panel._hover_on(None)


class Icons(unittest.TestCase):
    """Smooth at every size: pictures drawn larger and scaled down where
    the canvas cannot smooth, shapes where it can (a Mac)."""

    def test_every_icon_is_smoothed(self):
        for kind in ui_panel.ICONS:
            for scale in (1.0, 1.25, 1.5, 2.0):
                img = ui_panel.icon_image(kind, "#0A84FF", scale)
                (w, h), _ = ui_panel.ICONS[kind]
                self.assertEqual(img.size, (round(w * scale),
                                            round(h * scale)))
                alphas = set(img.getchannel("A").getdata())
                self.assertIn(0, alphas)
                # Edges in between, not a hard staircase.
                self.assertTrue(any(0 < a < 255 for a in alphas), kind)

    def test_gear_has_a_hole(self):
        img = ui_panel.icon_image("gear", "#000000", 2.0)
        w, h = img.size
        self.assertEqual(img.getpixel((w // 2, h // 2))[3], 0)


@unittest.skipIf(root is None, "no display")
class VectorIcons(unittest.TestCase):
    """The Mac path (shapes on the canvas) builds and recolours too."""

    def test_vector_panel(self):
        with mock.patch.object(ui_panel, "VECTOR_PLATES", True):
            ui_panel.MiniPanel._closed_at = 0.0
            panel = ui_panel.MiniPanel(
                root, theme.resolve("light"), on_snip=None, on_text=None,
                on_language=None, on_settings=None,
                status=lambda: ("Offline ready", "success"))
            self.addCleanup(panel.close)
            root.update()
            c = panel.canvas
            self.assertFalse([i for i in c.find_all()
                              if c.type(i) == "image"
                              and "icon_gear" in c.gettags(i)])
            panel._hover_on("gear")
            ink = [i for i in c.find_withtag("icon_gear")
                   if "ink" in c.gettags(i)]
            self.assertTrue(ink)
            self.assertEqual(c.itemcget(ink[0], "fill"),
                             theme.resolve("light")["text"])


class TrayClick(unittest.TestCase):
    """Windows: a left click opens the panel; the menu stays."""

    def menu(self, controller):
        from app import tray

        class Item:
            def __init__(self, text, action, **kw):
                self.text, self.action = text, action
                self.default = kw.get("default", False)
                self.visible = kw.get("visible", True)

        class Menu:
            SEPARATOR = None

            def __init__(self, *items):
                self.items = items

        fake = types.SimpleNamespace(MenuItem=Item, Menu=Menu)
        with mock.patch.object(tray, "pystray", fake):
            return tray.Tray(controller, None)._menu()

    def controller(self, panel=True):
        c = types.SimpleNamespace(
            config={"hotkey": "ctrl+alt+x", "hotkey_clipboard": "ctrl+alt+c",
                    "target_lang": "en"},
            calls=[])
        c.show_window = lambda: c.calls.append("window")
        c.trigger_snip = c.trigger_clipboard = c.quit = lambda: None
        c.set_language = lambda code: None
        if panel:
            c.request_panel = lambda: c.calls.append("panel")
        return c

    def test_left_click_is_the_panel(self):
        c = self.controller()
        menu = self.menu(c)
        defaults = [i for i in menu.items if i and i.default]
        self.assertEqual(len(defaults), 1)
        self.assertFalse(defaults[0].visible)
        defaults[0].action()
        self.assertEqual(c.calls, ["panel"])
        labels = [i.text for i in menu.items if i]
        self.assertIn("Open Squint…", labels)
        self.assertTrue(any(t.startswith("Snip") for t in labels))

    def test_without_panel_left_click_opens_window(self):
        c = self.controller(panel=False)
        menu = self.menu(c)
        defaults = [i for i in menu.items if i and i.default]
        self.assertEqual([d.text for d in defaults], ["Open Squint…"])


class AppWiring(unittest.TestCase):
    def test_pump_and_menubar_know_the_panel(self):
        from app import main
        with open(main.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('action == "panel"', src)
        self.assertIn("on_click=self.request_panel", src)
        self.assertTrue(hasattr(main.Controller, "show_panel"))

    def test_menubar_off_mac_is_harmless(self):
        from app import menubar
        if sys.platform == "darwin":
            self.skipTest("mac")
        self.assertFalse(menubar.start([], on_click=lambda: None))
        self.assertIsNone(menubar.anchor())

    def test_front_handle_off_platform(self):
        from app import platform_util
        if sys.platform in ("darwin", "win32"):
            self.skipTest("real platform")
        self.assertIsNone(platform_util.front_handle())
        self.assertFalse(platform_util.bring_back(123))


if __name__ == "__main__":
    unittest.main()
