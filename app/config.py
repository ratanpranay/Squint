"""Persistent settings + path resolution (works both from source and frozen)."""
import json
import os
import sys
import threading

from . import hotkey, platform_util

APP_NAME = "Squint"
# The app shipped as SnapTranslate first. data_dir() adopts the old
# settings folder so a rename does not wipe anyone's key.
OLD_APP_NAMES = ("SnapTranslate",)

DEFAULTS = {
    "target_lang": "en",
    # macOS convention is cmd+shift; Windows is ctrl+alt.
    "hotkey": platform_util.default_hotkeys()[0],
    "hotkey_clipboard": platform_util.default_hotkeys()[1],
    # Hold to see the whole screen translated in place (app/xray.py).
    "hotkey_xray": platform_util.default_xray_hotkey(),
    # The radial menu of everyday tools (app/radial). Windows for now.
    "hotkey_radial": "alt+space",
    "radial_enabled": True,
    # Which machinery delivers the global shortcut on macOS: "auto" tries
    # the system registration and falls back to watching the keyboard;
    # "carbon" and "watcher" pin it to one. A way out that does not need a
    # release, for the case where one of them stops delivering.
    "hotkey_backend": "auto",
    "auto_copy": False,              # copy translation to clipboard automatically
    "show_original": False,
    "popup_font_size": 12,
    "start_minimized": False,
    "run_at_startup": True,
    "ocr_upscale": 3.0,          # ceiling, not a fixed factor
    "theme": "light",           # auto | light | dark
    "translucent": False,       # see window_effects
    "window_effects": False,    # Windows compositing extras; off by default
    "overlay_mode": True,       # draw translations over the original text
    "close_on_click_away": True,
    # A small Squint icon beside text you select (app/select_icon.py).
    "select_icon": True,
    # Read the page you stop on in the background (app/preread.py).
    "read_ahead": False,
    # Pinch on a trackpad zooms the overlay. macOS only — everywhere else
    # a pinch already arrives as the wheel and this changes nothing. A way
    # to turn it off without a release, because it is the one part of the
    # overlay that reaches outside Tk to work at all.
    "pinch_zoom": True,
    # Translate text that is part of a picture — a wordmark, a caption
    # baked into a product shot, a title set across a photograph. Off:
    # covering those paints an opaque box across the artwork, and what
    # goes in the box is a translation of whatever the recogniser made of
    # type it cannot read. On, for anyone who would rather have the guess.
    "translate_pictures": True,
    # Set once the saved `translate_pictures` has been moved to the new
    # default. There was never a switch for it, so a saved False was only
    # ever the old default, not anybody's choice.
    "pictures_default_v2": True,
    "use_apple_vision": True,   # macOS: built-in OCR instead of Tesseract
    "last_export_dir": "",
    # Optional. The free services are rate-limited per IP address and the
    # ones that survive that are clumsier; a key sidesteps both.
    # "" means detect it; otherwise the display name of a language.
    "source_lang_name": "",
    # Which translation service answered last, so the next
    # launch does not rediscover it through timeouts.
    "last_backend": "",
    # Which service does the translating: "auto" walks the
    # fallback chain, anything else pins one.
    "engine": "auto",
    # The language of the app's own buttons and labels.
    "app_language": "en",
    # Gemini has a free API key and understands context, so it
    # is tried before the plain translation services.
    "gemini_api_key": "",
    "gemini_model": "",
    "google_api_key": "",
    # Google's free trial closes after 90 days unless upgraded; see
    # google_billing. When the key was set up, whether the user says the
    # account is upgraded, and which notices have been shown.
    "google_key_since": "",
    "google_key_tail": "",
    "google_upgraded": False,
    "google_upgrade_reminded": False,
    "google_billing_notice_at": "",
    "deepl_api_key": "",
    # A second free key with no card (console.groq.com), and the model its
    # list offered — remembered so the list is asked once, not per snip.
    "groq_api_key": "",
    # Google and DeepL rows shown under "Advanced translation". None until
    # the switch is first used: then open if one of their keys is saved.
    "show_advanced_keys": None,
    # Hy-MT2 on this computer (offline_model): switched on, and which size.
    "offline_enabled": False,
    "offline_model": "standard",
    "offline_tested": {},
    # The graphics-chip engine would not start here; use the processor.
    "offline_gpu_failed": False,
    # The Mac app's Tk 8.6 swap was tried and could not be done.
    "tk86_swap_failed": False,
    # Weekly check for a newer Hy-MT2 file (offline_model.check_for_update).
    "check_offline_updates": True,
    "offline_update_checked": 0,
    "offline_update_available": False,
    "offline_sha": {},
    # The newer app build the last check found, for the dot on Updates.
    "update_available": "",
    # The last verdict on each key, shown as the dot beside it.
    "key_checks": {},
    "groq_model": "",
    # Whether the first-run screens (language + key) have been shown.
    # Set on Finish and on closing the window either way — asked once,
    # never nagged about again.
    "setup_complete": False,
}

_lock = threading.Lock()


def app_dir():
    """Directory containing bundled resources."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir():
    """Where PyInstaller unpacks --add-data payloads."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", app_dir())
    return app_dir()


def _data_base():
    if platform_util.IS_MAC:
        return os.path.expanduser("~/Library/Application Support")
    if platform_util.IS_WINDOWS:
        return os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.environ.get("APPDATA") or os.path.expanduser("~/.config")


def data_dir():
    """Where settings, models and the log live — per platform convention.

    The app used to be called SnapTranslate, and everything a user has —
    their API key, their downloaded languages, their shortcuts — sits in a
    folder named after it. Renaming the app without moving that folder
    would silently reset all of it, so the old one is adopted once and
    then forgotten about.
    """
    base = _data_base()
    d = os.path.join(base, APP_NAME)
    if not os.path.isdir(d):
        for was in OLD_APP_NAMES:
            old = os.path.join(base, was)
            if os.path.isdir(old):
                try:
                    os.rename(old, d)
                    break
                except Exception:
                    # Renaming can fail if the old folder is in use. Falling
                    # back to a copy keeps the settings; a stale duplicate is
                    # a smaller problem than losing a paid API key.
                    try:
                        import shutil
                        shutil.copytree(old, d)
                        break
                    except Exception:
                        pass
    os.makedirs(d, exist_ok=True)
    return d


def config_path():
    return os.path.join(data_dir(), "config.json")


def log_path():
    return os.path.join(data_dir(), "squint.log")


def tessdata_dir():
    """User-writable tessdata dir; seeded from the bundled copy on first run."""
    d = os.path.join(data_dir(), "tessdata")
    os.makedirs(d, exist_ok=True)
    return d


def bundled_tesseract_dir():
    for candidate in (
        os.path.join(resource_dir(), "tesseract"),
        os.path.join(app_dir(), "tesseract"),
        os.path.join(app_dir(), "vendor", "tesseract"),
        os.path.join(app_dir(), "build", "tesseract"),
    ):
        if os.path.isfile(os.path.join(candidate, "tesseract.exe")):
            return candidate
    return None


# Combinations that turned out to belong to something else. A stored value
# is only replaced if the user never changed it away from that default.
BAD_HOTKEYS = {
    "cmd+shift+t": "ctrl+cmd+t",     # browsers: reopen closed tab
    "cmd+shift+c": "ctrl+cmd+c",     # browsers: developer tools
}


class Config(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
        self.load()
        self.migrate()

    def migrate(self):
        """Fix settings saved by an older version.

        Defaults are only consulted on a first run, so a bad default that has
        already been written to disk would otherwise persist forever.
        """
        changed = False
        # Text on a picture is translated in place now, like any other text.
        # It used to be left alone by default, and every snip of a slide or
        # a product page came back as a card instead of the overlay.
        if not self.get("pictures_default_v2"):
            self["translate_pictures"] = True
            self["pictures_default_v2"] = True
            changed = True
        defaults = platform_util.default_hotkeys()
        # The snip shortcut moved from T to X (1.48.37). Only a shortcut
        # still at the old default moves, and only once: somebody who picks
        # T again afterwards keeps it.
        if not self.get("snip_on_x_v1"):
            if str(self.get("hotkey", "")).lower() in ("ctrl+alt+t",
                                                       "ctrl+cmd+t"):
                self["hotkey"] = defaults[0]
            self["snip_on_x_v1"] = True
            changed = True
        for index, key in enumerate(("hotkey", "hotkey_clipboard")):
            current = str(self.get(key, "")).lower()
            if platform_util.IS_MAC and current in BAD_HOTKEYS:
                self[key] = BAD_HOTKEYS[current]
                changed = True
            elif platform_util.IS_MAC and hotkey.forbidden(current):
                # Bare Cmd+letter globally — Cmd+C, Cmd+Q, whatever it is —
                # should never have been storable, but this runs on every
                # launch regardless of how one got in, so nothing that
                # already hijacked a system shortcut survives an update.
                self[key] = defaults[index]
                changed = True
        if changed:
            self.save()
        return changed

    def load(self):
        try:
            with open(config_path(), "r", encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                for k, v in stored.items():
                    if k in DEFAULTS:
                        self[k] = v
                # Saved by a version from before the pictures default
                # moved: its `translate_pictures` is the old default.
                if "pictures_default_v2" not in stored:
                    self["pictures_default_v2"] = False
        except Exception:
            pass

    def save(self):
        with _lock:
            try:
                tmp = config_path() + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(dict(self), fh, indent=2)
                os.replace(tmp, config_path())
            except Exception:
                pass

    def set(self, key, value):
        changed = self.get(key) != value
        self[key] = value
        self.save()
        if changed and key in TRANSLATION_SETTINGS:
            # A translation remembered under the old setting would be
            # shown under the new one: forget them all.
            try:
                from . import translator, xray
                translator.forget()
                xray.forget()
            except Exception:
                pass


# Settings that change what a translation comes out as.
TRANSLATION_SETTINGS = {
    "engine_profile", "target_lang", "source_lang_name", "gemini_api_key",
    "groq_api_key", "google_api_key", "deepl_api_key", "glossary",
    "always_cloud_read", "offline_model",
}


CONFIG = Config()


def build_id():
    """The build stamp from VERSION.txt, e.g. '2026-08-29 22:30 UTC (g)'.

    Shown in the window because "did the new version actually install?" has
    come up repeatedly, and a folder date does not answer it — the app that
    is running does.
    """
    try:
        path = os.path.join(app_dir(), "VERSION.txt")
        with open(path, "r", encoding="utf-8") as fh:
            first = fh.readline().strip()
        # "Squint 1.0.0" since the versions got names; "Squint build
        # 2026-08-31 (ba)" before that. Both are read, because an update
        # replaces VERSION.txt but the app that reads it first is the old
        # one, and a build stamp of "unknown" makes the updater think
        # every release is newer.
        for prefix in ("Squint build ", "SnapTranslate build ", "Squint "):
            if first.startswith(prefix):
                return first[len(prefix):].strip() or "unknown"
        return first.strip() or "unknown"
    except Exception:
        return "unknown"
