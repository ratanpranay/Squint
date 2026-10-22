"""Build the real tray menu against pystray's real validation.

pystray inspects every menu action's argument count and raises ValueError on
anything it cannot call — a check that only fires when the menu is built, i.e.
at startup on the user's machine. This exercises it here instead, without
needing a Windows tray or a GTK display.
"""
import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _find_base_py():
    for root in sys.path:
        candidate = os.path.join(root, "pystray", "_base.py")
        if os.path.isfile(candidate):
            return candidate
    raise SystemExit("pystray is not installed; run: pip install pystray")


def _install_headless_pystray():
    """Expose pystray's platform-independent Menu/MenuItem as `pystray`."""
    candidate = _find_base_py()

    pkg = types.ModuleType("pystray")
    pkg.__path__ = [os.path.dirname(candidate)]
    sys.modules["pystray"] = pkg
    spec = importlib.util.spec_from_file_location("pystray._base", candidate)
    base = importlib.util.module_from_spec(spec)
    sys.modules["pystray._base"] = base
    spec.loader.exec_module(base)

    pkg.Menu = base.Menu
    pkg.MenuItem = base.MenuItem

    class Icon:
        def __init__(self, name, image=None, title=None, menu=None):
            self.name, self.image, self.title, self.menu = (
                name, image, title, menu)

        def run_detached(self):
            return True

        def update_menu(self):
            return True

        def notify(self, *a, **k):
            return True

        def stop(self):
            return True

    pkg.Icon = Icon
    return pkg


def main():
    _install_headless_pystray()

    from app import config
    from app.tray import Tray, load_image

    calls = []

    class FakeController:
        def __init__(self):
            self.config = config.CONFIG

        def trigger_snip(self):
            calls.append("snip")

        def trigger_clipboard(self):
            calls.append("clip")

        def show_window(self):
            calls.append("show")

        def quit(self):
            calls.append("quit")

        def set_language(self, code):
            calls.append(("lang", code))
            self.config["target_lang"] = code

    controller = FakeController()
    controller.config["target_lang"] = "en"

    tray = Tray(controller, load_image(os.path.join(ROOT, "assets",
                                                    "icon.png")))
    assert tray.start() is True, "tray.start() reported failure"
    print("tray started, icon=%s" % (tray.icon is not None))

    # Walk every item, exactly as the platform backend does when it renders.
    def walk(menu, depth=0):
        seen = 0
        for item in menu:
            label = str(item)
            submenu = getattr(item, "submenu", None)
            checked = item.checked          # invokes the checked callable
            print("%s- %-28s checked=%s" % ("  " * depth, label[:28], checked))
            seen += 1
            if submenu:
                seen += walk(submenu, depth + 1)
        return seen

    total = walk(tray.icon.menu)
    print("menu items rendered: %d" % total)

    # Invoke each action the way pystray does: action(icon, item).
    def invoke_all(menu):
        for item in menu:
            submenu = getattr(item, "submenu", None)
            if submenu:
                invoke_all(submenu)
            else:
                item(tray.icon)

    invoke_all(tray.icon.menu)
    print("actions invoked ->", calls)

    assert "snip" in calls, "snip action never fired"
    assert "clip" in calls, "clipboard action never fired"
    assert "show" in calls, "open-window action never fired"
    assert "quit" in calls, "quit action never fired"
    langs = [c for c in calls if isinstance(c, tuple)]
    assert langs, "no language item fired"
    print("language items fired: %d (e.g. %s)" % (len(langs), langs[0]))

    # The radio ticks must follow the current setting.
    controller.config["target_lang"] = "de"
    labels = {}

    def collect(menu):
        for item in menu:
            submenu = getattr(item, "submenu", None)
            if submenu:
                collect(submenu)
            else:
                labels[str(item)] = item.checked

    collect(tray.icon.menu)
    assert labels.get("German") is True, "German should be ticked: %s" % labels
    assert labels.get("English") is False, "English should not be ticked"
    print("radio state tracks config: German=True, English=False")

    tray.refresh()
    tray.notify("hello")
    tray.stop()
    print("\nTRAY SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
