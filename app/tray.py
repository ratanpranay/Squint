"""System-tray icon. Runs detached so Tk keeps the main loop."""
import threading

from PIL import Image

try:
    import pystray
except Exception:  # pragma: no cover
    pystray = None

from .langs import name_for, TARGET_LANGUAGES

# Languages offered directly in the tray menu (the rest live in the window).
QUICK_LANGS = ["en", "hi", "de", "fr", "es", "zh-CN", "ja", "ar", "ru", "pt"]


class Tray:
    def __init__(self, controller, image):
        self.controller = controller
        self.image = image
        self.icon = None
        self._lock = threading.Lock()

    def _menu(self):
        c = self.controller

        def lang_item(code):
            # pystray inspects the action's argument count and rejects
            # anything over two — so the usual `lambda ..., code=code:`
            # late-binding trick is not available here (the default counts
            # as a third parameter). A closure carries the value instead.
            def activate(icon, item):
                c.set_language(code)

            def is_current(item):
                return c.config["target_lang"] == code

            return pystray.MenuItem(name_for(code), activate,
                                    checked=is_current, radio=True)

        # The bold one at the top is what a left click does, and it used to
        # be the snip. That is the wrong thing to put on the one gesture
        # somebody makes by accident: a stray click dimmed the whole screen
        # and waited for a selection, over whatever they were doing. And it
        # was the one action already on a global shortcut, so the click was
        # never the way anybody reached it deliberately.
        #
        # Opening the window is the safe default — nothing happens to the
        # screen, the snip button is right there, and every other way in is
        # unchanged.
        # A left click now opens the small panel (app/ui_panel.py): Snip
        # and Text, the language, and whether offline is ready - nothing
        # happens to the screen, and the window is behind its gear. The
        # item is hidden: it is what the click does, not a line in this
        # menu, which stays the right click.
        panel = getattr(c, "request_panel", None)
        first = []
        if panel is not None:
            first = [pystray.MenuItem("Squint", lambda: panel(),
                                      default=True, visible=False)]
        return pystray.Menu(
            *first,
            pystray.MenuItem(
                "Snip && translate  (%s)" % c.config["hotkey"].upper(),
                lambda: c.trigger_snip()),
            pystray.MenuItem(
                "Translate clipboard  (%s)"
                % c.config["hotkey_clipboard"].upper(),
                lambda: c.trigger_clipboard()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Translate into",
                pystray.Menu(*[lang_item(code) for code in QUICK_LANGS
                               if code in TARGET_LANGUAGES])),
            pystray.MenuItem("Open Squint…", lambda: c.show_window(),
                             default=panel is None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: c.quit()),
        )

    def start(self):
        if pystray is None:
            return False
        self.icon = pystray.Icon("Squint", self.image,
                                 "Squint", self._menu())
        try:
            self.icon.run_detached()
            return True
        except Exception:
            # Fall back to a plain thread; works on most Windows setups.
            threading.Thread(target=self.icon.run, daemon=True).start()
            return True

    def refresh(self):
        if self.icon is None:
            return
        with self._lock:
            try:
                self.icon.menu = self._menu()
                self.icon.update_menu()
            except Exception:
                pass

    def notify(self, message, title="Squint"):
        if self.icon is None:
            return
        try:
            self.icon.notify(message, title)
        except Exception:
            pass

    def stop(self):
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass


def load_image(path):
    try:
        return Image.open(path)
    except Exception:
        return Image.new("RGBA", (64, 64), (61, 125, 255, 255))
