"""Squint — entry point and controller."""
import ctypes
import atexit
import os
import queue
import sys
import threading
import time
import tkinter as tk
import traceback
from tkinter import messagebox

from . import (config, hotkey, ocr, overlay, platform_util, snip,
               theme as theme_mod, translator)
from .langs import name_for
from .ui_result import OverlayWindow, ResultPopup, StatusToast

CFG = config.CONFIG
MUTEX_NAME = "Global\\Squint_SingleInstance_v1"

# How often to check that the global shortcuts are still being listened
# for. Cheap — one look at whether a process is alive — and it is the
# difference between a shortcut that stops working until the next restart
# and one that comes back on its own.
HOTKEY_CHECK = 30000
# How often Windows is asked which app is in front (see _track_front).
FRONT_EVERY = 500

# How many finished translations to keep. A snip closes and is gone, and
# getting it back means finding the document again and drawing the same
# rectangle a second time — which is never quite the same rectangle. Five
# is enough to cover an afternoon of going back and forth between two
# documents, and small enough that the pictures behind them are not a
# memory problem.
RECENT_KEEP = 5


def log(message):
    try:
        with open(config.log_path(), "a", encoding="utf-8") as fh:
            fh.write(message.rstrip() + "\n")
    except Exception:
        pass


def already_running():
    """Is a copy of Squint already up? Named mutex on Windows.

    There was no macOS half of this at all, and it showed the moment
    somebody had two copies of Squint.app on disk: both launched, both
    drew a window, and both registered the same global shortcut — so the
    hotkey went to whichever had claimed it, and quitting one did not give
    it back. Two windows is the visible symptom; two hotkey registrations
    is the one that makes the app feel broken.
    """
    if os.name == "nt":
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW(None, False, MUTEX_NAME)
            return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
        except Exception:
            return False
    return _unix_lock_taken()


# Held for the life of the process. A local, not a global, and the file
# handle would be closed the moment the function returned.
_single_lock = None


def _unix_lock_taken():
    """A lock file the operating system releases when the process dies.

    Not a PID file. A PID file left behind by a crash reads as "already
    running" for ever, and the usual answer to that — checking whether the
    PID is alive — is wrong in its own way, because PIDs are reused. flock
    is held by the kernel and let go when the process ends, however it
    ends, which is the property actually wanted here.
    """
    global _single_lock
    try:
        import fcntl
        import tempfile
        path = os.path.join(tempfile.gettempdir(), "squint-single.lock")
        handle = open(path, "w")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return True
        _single_lock = handle          # kept open on purpose
        return False
    except Exception:
        # Never refuse to start over a failure in the guard itself. Two
        # windows is a nuisance; no window is the app not working.
        return False


def clip_is_stale(content, seen_now, seen_before, text_seen):
    """Whether the clipboard, fallen back on after a failed copy, still
    holds what it held when the shortcut was last used - the text from
    before, not something copied by hand for this. By the clipboard's
    change counter where there is one (Windows, macOS), else by the text."""
    if not content:
        return False
    if seen_now is not None and seen_before is not None:
        return seen_now == seen_before
    return content.strip() == str(text_seen or "").strip()


def zoomer(image, lines, texts, target, floor):
    """A function that lays the same page out again at a new size.

    Zooming redraws rather than magnifying: enlarging the finished picture
    makes the letters bigger and no easier to read. It is a closure over
    the page and its translation, which is why changing the language has
    to build a new one — the old one would redraw the old language.
    """

    def again(factor):
        from PIL import Image as _Im
        big = image.resize((max(1, int(image.width * factor)),
                            max(1, int(image.height * factor))), _Im.LANCZOS)
        grown, grown_tall = overlay.layout(
            big, overlay.scale_lines(lines, factor), texts, target,
            min_size=max(floor, int(floor * factor)))
        return big, grown, grown_tall

    return again


# A snip cancelled while it works carries on in the background, and what it
# finds is kept this long: snip the same area again and it is shown at once.
READY_KEEP = 300.0
# How long a new snip waits for a cancelled one of much the same area (or a
# page being prepared ahead) before doing the work itself.
SETTLE_WAIT = 20.0


class _SnipJob:
    """One snip's reading and translating, and where its result goes."""

    def __init__(self, key, toast, stop):
        self.key = key
        self.toast = toast            # the indicator it reports to now
        self.stop = stop
        self.finished = False
        self.done = threading.Event()


def _overlap(a, b):
    """Share of rectangle b (x, y, w, h) that lies inside rectangle a."""
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1 = min(a[0] + a[2], b[0] + b[2])
    y1 = min(a[1] + a[3], b[1] + b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0) / float(max(1.0, b[2] * b[3]))


class Controller:
    def __init__(self):
        self.config = CFG
        self.root = tk.Tk()
        # Every callback in this app runs inside Tk, and Tk's default
        # answer to an exception in one is to print it to a console that a
        # packaged app does not have. What the user sees is a button that
        # did nothing, or a window half drawn and then abandoned — and
        # nothing written down anywhere to say why.
        #
        # One handler, at the root, turns every one of those into a line in
        # the log. It does not make the fault go away; it makes the fault
        # reportable, which is the difference between "it crashes a lot"
        # and a traceback naming the line.
        self.root.report_callback_exception = self._callback_failed
        self.root.withdraw()
        self.root.title("Squint")
        self.queue = queue.Queue()
        self.busy = threading.Lock()
        self.xray = None
        self._last_put_on_clipboard = None
        # The last few finished translations, newest first.
        self.recent = []
        # Load the recogniser while the user is still deciding what to
        # snip, not while they are watching a toast. Daemon, so it can
        # never hold the app open, and silent, so a failure here is
        # invisible rather than alarming.
        threading.Thread(target=self._warm_reader, daemon=True).start()
        self.window = None
        self.tray = None
        self.hotkeys = None
        self.hk_snip_id = None
        self.hk_clip_id = None
        # The first-run wizard, while it is still on screen. Startup can
        # decide, entirely on its own timing, that the main window needs
        # to be shown (no tray icon, a hotkey conflict) — see
        # _first_run_open, _warn_no_tray and _warn_hotkeys.
        self._first_run = None
        # Whether the user has been told that macOS is blocking the copy.
        # Once per run: the shortcut is pressed dozens of times a day and
        # the same paragraph of instructions each time is noise, not help.
        self._told_permission = False
        self._palette = theme_mod.resolve(CFG.get("theme", "auto"))

        # Do this before any window exists, or macOS keeps the process in
        # the background and nothing the app shows will come forward.
        log("activation : %s" % platform_util.become_foreground_app())

        self.icon_path = self._find_asset("icon.ico")
        png = self._find_asset("icon.png")
        # The Dock picks its icon from the app bundle only when the running
        # interpreter is the one inside it. When the launcher had to fall
        # back to the unpacked Python, the Dock showed a blank page; set it
        # here so it is Squint's either way.
        if png:
            log("dock icon  : %s" % platform_util.set_dock_icon(png))
        if self.icon_path:
            try:
                self.root.iconbitmap(self.icon_path)
            except Exception:
                pass

        from .ui_main import MainWindow
        self.window = MainWindow(self)
        log("chrome     : %s" % (self.window.effects,))
        self.window.withdraw()

        # No welcome screen any more: the main window explains itself, and
        # keys, languages and permissions all have their place in it. The
        # wizard stayed behind as a window that could sit over Settings
        # and take its scrolling.
        if not CFG.get("setup_complete", False):
            CFG.set("setup_complete", True)

        self._register_mac_reopen()
        self._start_menubar()
        self._start_tray(png or self.icon_path)
        self._start_select_icon()
        if sys.platform == "win32":
            self.root.after(FRONT_EVERY, self._track_front)
        self._start_hotkeys()
        # No reading ahead. It read the whole screen in the background
        # every few seconds, and the whole screen again at every press of
        # the shortcut, at the same moment as the snip's own reading: on a
        # 4K screen 2-4 s each, all day, growing slower as the day went on,
        # and a snip that reads in 0.2 s took 2.5 s beside it. A snip reads
        # its own area (1.49.0), so nothing used what it read.
        self.root.after(60, self._pump)
        # A crash or a kill is not a clean quit, and a global hotkey left
        # registered by a dead process is a shortcut that does nothing
        # until the machine is restarted.
        atexit.register(self.release)
        threading.Thread(target=self._warm_up, daemon=True).start()
        # Look for a new build once a day, quietly. An Update button in
        # Settings is a button nobody presses — most people never open
        # Settings again after the first day — so without this a release
        # would sit unnoticed and the whole mechanism would be theatre.
        from . import updater
        self.root.after(updater.CHECK_DELAY_MS, self._check_updates_quietly)

    def _callback_failed(self, kind, value, trace):
        """Write down a failure inside a Tk callback and carry on.

        Deliberately not a dialog. These arrive from timers and redraws as
        much as from buttons, so a box on screen could appear over and over
        with nothing the user can do about it — and the one that matters is
        usually the first, which a stack of identical boxes buries.
        """
        try:
            import traceback as _tb
            log("callback   : " + "".join(
                _tb.format_exception(kind, value, trace)).rstrip())
        except Exception:
            pass

    def _show_first_run(self):
        """The welcome/language/key screens.

        Shown once automatically, at first launch. Parented to the hidden root rather
        than the withdrawn main window — both are toplevels either way,
        but the main window has no reason to exist yet the first time this
        runs, and tying the dialog's lifetime to it would be an assumption
        this does not need to make.
        """
        if self._first_run_open():
            # Called again while it is already open (Settings, pressed
            # twice) — bring the one that exists forward rather than
            # opening a second copy on top of it.
            try:
                platform_util.raise_to_front(self._first_run)
            except Exception:
                pass
            return
        try:
            from .ui_firstrun import FirstRunSetup
            self._first_run = FirstRunSetup(self.root)
        except Exception:
            log(traceback.format_exc())
            # Never let a broken dialog block the app from starting. Worst
            # case, this run is missing a language/key it would otherwise
            # have set, and both remain reachable from Settings.
            CFG.set("setup_complete", True)

    # How often a running app asks itself whether a check is due. The
    # checks themselves are daily (app) and weekly (offline model); this
    # only lets an app that stays open for a week notice either.
    UPDATE_POLL_MS = 3600 * 1000

    def _check_updates_quietly(self):
        """Fetch one small file in the background; mention anything new.
        Then, weekly, whether the offline model has a newer version. Runs
        again every hour; each check decides for itself if it is due."""
        from . import updater, offline_model

        def work():
            release = updater.check_quietly()
            if release is not None:
                self.queue.put(("update_found", release))
            try:
                if offline_model.update_check_due():
                    offline_model.check_for_update()
            except Exception:
                pass
            self.queue.put(("update_dot", None))

        threading.Thread(target=work, daemon=True).start()
        try:
            self.root.after(self.UPDATE_POLL_MS, self._check_updates_quietly)
        except Exception:
            pass

    def _toolkit_ready(self):
        try:
            self.window.say_toolkit_ready()
        except Exception:
            pass

    def _refresh_update_dot(self):
        try:
            self.window.refresh_update_dot()
        except Exception:
            pass

    def _announce_update(self, release):
        """Say it once, in the window, and leave the decision alone.

        Not a dialog. An update is never urgent enough to interrupt what
        someone is in the middle of, and a modal that appears over the
        document they were reading is exactly the behaviour that teaches
        people to dismiss update prompts without reading them.
        """
        from . import updater
        updater.mark_mentioned(release.build)
        try:
            self.window.show_update_available(release)
        except Exception:
            log(traceback.format_exc())

    def _warm_up(self):
        """Pay the one-off costs at launch instead of on the first snip.

        The first translation of a session otherwise includes DNS, TCP and
        TLS setup, and the first OCR call pays for loading the language model
        off disk. Doing both now makes the first shortcut feel like the
        tenth.
        """
        try:
            translator.warm_up(CFG.get("target_lang", "en"))
        except Exception:
            pass
        # The Mac app's Tk 9 crashes when screens change; swap in 8.6.
        try:
            from . import mac_toolkit
            if mac_toolkit.needed():
                log("toolkit    : Tk %s, swapping in 8.6"
                    % mac_toolkit.current_tk())
                mac_toolkit.start(lambda ok, _m: ok and self.queue.put(
                    ("toolkit_ready", None)))
        except Exception:
            log(traceback.format_exc())
        # Deliberately not warming Vision here. Apple's frameworks are
        # reached through pyobjc, and calling into them from a stray worker
        # thread is exactly the pattern that already crashed this app once
        # (Text Input Services). Tesseract is a subprocess and safe to warm.
        try:
            if not ocr.use_vision():
                from PIL import Image as _Image
                ocr.ensure_ready()
                ocr.image_to_text(_Image.new("RGB", (140, 40), "white"))
        except Exception:
            pass

    # -- setup ---------------------------------------------------------
    def palette(self):
        """Current colour scheme, re-resolved so 'auto' follows Windows."""
        self._palette = theme_mod.resolve(CFG.get("theme", "auto"))
        return self._palette

    def _find_asset(self, name):
        for base in (config.resource_dir(), config.app_dir()):
            for candidate in (os.path.join(base, "assets", name),
                              os.path.join(base, name)):
                if os.path.isfile(candidate):
                    return candidate
        return None

    def _start_menubar(self):
        """Put an icon in the menu bar, so the app can live out of the way.

        Created here, on Tk's own thread, which is the main thread — the
        rule AppKit insists on and the one the old pystray tray broke.
        Never fatal: a missing icon costs convenience, not the app.
        """
        from . import menubar
        if not menubar.available():
            log("menubar    : unavailable (%s)" % menubar.last_error())
            return
        actions = [
            # One ampersand. The doubled one in tray.py is correct *there* —
            # that menu is drawn by a toolkit where & marks the underlined
            # access key and && is how you ask for a literal one. AppKit
            # has no such escape, so it prints exactly what it is given.
            ("Snip & Translate", lambda: self.queue.put(("snip", None))),
            ("Translate Clipboard", lambda: self.queue.put(("clip", None))),
            (None, None),
            # The same switcher the tray has had on Windows since it was
            # written. Without it, changing target language on a Mac meant
            # opening the window for a setting that is one click away
            # everywhere else.
            ("Translate into", self._language_actions()),
            (None, None),
            ("Open Squint", lambda: self.queue.put(("show", None))),
            (None, None),
            ("Quit", lambda: self.queue.put(("quit", None))),
        ]
        # A click on the icon opens the small panel (app/ui_panel.py);
        # this menu is the right click.
        ok = menubar.start(actions, on_click=self.request_panel)
        log("menubar    : %s" % ("started" if ok else menubar.last_error()))
        if ok and menubar._state.get("click_error"):
            log("menubar    : panel unavailable (%s), menu on click"
                % menubar._state["click_error"])

    # -- the small panel ---------------------------------------------
    def request_panel(self):
        """The icon was clicked. Any thread: the panel opens on Tk's."""
        self.queue.put(("panel", None))

    def show_panel(self):
        """Open the panel from the menu-bar or tray icon, or close it if
        it is open."""
        from .ui_panel import MiniPanel, status_line
        from .shortcut_field import pretty
        try:
            if not MiniPanel.is_open():
                # Who to give the keyboard back to for Text: the app in
                # front when the icon was clicked. On Windows the click
                # itself puts the taskbar in front, so it is the last
                # app seen before that.
                front = platform_util.front_handle()
                if sys.platform == "win32" or not front:
                    front = getattr(self, "_last_front", None) or front
                self._panel_front = front
                self._front_before_clip = platform_util.frontmost_app()
            anchor = None
            if sys.platform == "darwin":
                from . import menubar
                anchor = menubar.anchor()
            panel = MiniPanel.toggle(
                self.root, self.palette(),
                on_snip=self.trigger_snip, on_text=self._panel_text,
                on_language=self.set_language, on_settings=self.show_window,
                language=CFG.get("target_lang", "en"),
                keys=(pretty(CFG.get("hotkey", "")),
                      pretty(CFG.get("hotkey_clipboard", ""))),
                status=status_line, anchor=anchor)
            if panel is not None:
                log("panel      : open")
                self._keep_main_window_back()
        except Exception:
            log("panel failed:\n%s" % traceback.format_exc())
            self.show_window()

    def _panel_text(self):
        """Text, from the panel: the app that was in front gets the
        keyboard back first, so the copy reaches the selected text."""
        if platform_util.bring_back(getattr(self, "_panel_front", None)):
            self.root.after(180, self.trigger_clipboard)
        else:
            self.trigger_clipboard()

    # -- run check (app/selfcheck.py) ------------------------------------
    def run_check(self):
        """Three test pages through the whole snip, on this computer; the
        result in a card and in selfcheck.txt beside the log."""
        if getattr(self, "_checking", False):
            return
        self._checking = True
        log("check      : started")
        toast = StatusToast(self.root, "Running check…",
                            palette=self.palette())

        def work():
            try:
                from . import selfcheck
                outcome = selfcheck.run(controller=self, translator=translator,
                                        log=log)
            except Exception as exc:
                log(traceback.format_exc())
                outcome = (False, "The check could not run: %s" % exc, "")
            self.queue.put(("check_done", (toast,) + tuple(outcome)))
        threading.Thread(target=work, daemon=True, name="run-check").start()

    def _check_done(self, toast, passed, summary, path):
        self._checking = False
        try:
            toast.close()
        except Exception:
            pass
        where = ("\n\nThe full report is in %s - send it with the log."
                 % path) if path else ""
        try:
            ResultPopup(self.root, summary + where, "",
                        "Run check: %s" % ("passed" if passed else "FAILED"),
                        show_original=False,
                        font_size=int(CFG.get("popup_font_size", 12)),
                        palette=self.palette(),
                        kind="result" if passed else "error")
        except Exception:
            log(traceback.format_exc())

    # -- the icon beside selected text (app/select_icon.py) -----------
    def _start_select_icon(self):
        try:
            from . import select_icon
            self._select = select_icon.Watcher(
                self.root, self._select_icon_clicked,
                blocked=self._select_blocked, log=log)
            if CFG.get("select_icon", True):
                self._select.start()
            log("select icon: %s" % ("on" if CFG.get("select_icon", True)
                                     else "off"))
        except Exception:
            self._select = None
            log("select icon unavailable:\n%s" % traceback.format_exc())

    def set_select_icon(self, on):
        CFG.set("select_icon", bool(on))
        watcher = getattr(self, "_select", None)
        if watcher is None:
            return
        if on:
            watcher.start()
        else:
            watcher.stop()

    def _select_blocked(self):
        """Not while Squint is busy with the screen: a snip being drawn,
        hold-to-see, a translation on its way."""
        try:
            if self.busy.locked():
                return True
            xray = self.xray
            if xray is not None and (xray.win is not None or xray.opening):
                return True
        except Exception:
            pass
        return False

    def _select_icon_clicked(self, text, handle):
        """The icon was clicked. With the selected text in hand (a Mac told
        us what it is), translate that; otherwise give the keyboard back to
        the app it is in and copy it, as Ctrl+Alt+C does."""
        if not text and sys.platform == "darwin":
            # Asked now that the selection has settled (select_icon).
            try:
                from . import select_icon
                text = select_icon.mac_selection_now(handle) or None
            except Exception:
                text = None
        log("select icon: clicked (%s)" % ("text from the system" if text
                                          else "copying the selection"))
        if text:
            self._front_before_clip = platform_util.frontmost_app()
            self.trigger_clipboard(given=text)
            return
        if platform_util.bring_back(handle):
            self.root.after(150, self.trigger_clipboard)
        else:
            self.trigger_clipboard()

    def _track_front(self):
        """Windows: the last app in front that was not Squint or the
        taskbar - see show_panel. One cheap call twice a second."""
        try:
            front = platform_util.front_handle()
            if front:
                self._last_front = front
        except Exception:
            pass
        try:
            self.root.after(FRONT_EVERY, self._track_front)
        except Exception:
            pass

    def _language_actions(self):
        """The quick-pick languages, as (name, callback) pairs.

        The same list the tray uses, so the two menus offer the same
        choices rather than drifting into two different opinions about
        which languages are worth one click.
        """
        from .langs import TARGET_LANGUAGES, name_for
        from .tray import QUICK_LANGS
        out = []
        for code in QUICK_LANGS:
            if code not in TARGET_LANGUAGES:
                continue

            def pick(_code=code):
                self.set_language(_code)

            out.append((name_for(code), pick))
        return out

    def _start_tray(self, image_path):
        """Start the tray icon. Never fatal — the app works without it.

        The shortcuts and the main window are the product; the tray is a
        convenience. A tray that refuses to start should cost the user an
        icon, not the whole application.
        """
        if not platform_util.tray_supported():
            self.tray = None
            log("tray     : skipped (not safe on this platform)")
            self.root.after(400, self._no_tray_window_mode)
            return
        try:
            from .tray import Tray, load_image
            self.tray = Tray(self, load_image(image_path) if image_path
                             else load_image(""))
            if not self.tray.start():
                raise RuntimeError("tray backend unavailable")
        except Exception:
            self.tray = None
            log("tray unavailable:\n%s" % traceback.format_exc())
            self.root.after(800, self._warn_no_tray)

    def _first_run_open(self):
        """Whether the first-run wizard is still on screen.

        A window that shows itself unprompted, on its own timer, needs to
        know this before doing so — otherwise it lands in front of a wizard
        that raised itself properly a moment earlier and nothing ever
        raises the wizard again. See _warn_no_tray and _warn_hotkeys, the
        two paths that found this the hard way: a fresh install is exactly
        when a hotkey conflict or a missing tray backend is likeliest, and
        exactly when the wizard is likeliest to still be open.
        """
        fr = self._first_run
        if fr is None:
            return False
        try:
            return bool(fr.winfo_exists())
        except Exception:
            return False

    def _no_tray_window_mode(self):
        """Decide what closing the window means.

        With a menu-bar icon there is always a way back, so closing hides.
        Without one the window is the only entrance, and hiding it would
        strand the user with a running app they cannot reach.
        """
        if self.window is None:
            return
        from . import menubar
        if menubar.last_error() == "" and menubar.available():
            self.window.protocol("WM_DELETE_WINDOW", self.window.hide)
        else:
            self.window.protocol("WM_DELETE_WINDOW", self.quit)

    def _warn_no_tray(self):
        """Without a tray icon the window is the only way back in, so it must
        not vanish when closed."""
        if self.window is None:
            return
        self.window.protocol("WM_DELETE_WINDOW", self.quit)
        if self._first_run_open():
            # Showing the main window now would put it in front of the
            # wizard, which raised itself once already and has no reason
            # to expect anything is about to jump the queue. Try again
            # shortly rather than fight over which window is on top.
            self.root.after(800, self._warn_no_tray)
            return
        self.window.show()
        try:
            self.window._show_pane("Settings")
            self.window._set_hk_status(
                "The tray icon could not start, so closing this window "
                "exits the app. The shortcuts work either way.",
                self._palette["warning"])
        except Exception:
            pass

    def _register_mac_reopen(self):
        """Bring the window back when the Dock icon is clicked.

        Closing the window only hides it — the app stays running so the
        shortcut keeps working. Without this, that is a trap: there is no
        tray icon on macOS, so clicking the Dock icon did nothing and the
        window could not be recovered at all.

        Tk exposes the Dock's reopen event as a command it will call if one
        exists, which avoids installing an NSApplicationDelegate of our own —
        Tk already owns that, and replacing it breaks its event handling.
        """
        if not platform_util.IS_MAC:
            return
        for name, handler in (("::tk::mac::ReopenApplication",
                               self._reopened),
                              ("::tk::mac::OpenApplication",
                               self._reopened)):
            try:
                self.root.createcommand(name, handler)
                log("dock       : %s registered" % name)
            except Exception as exc:
                log("dock       : %s failed (%s)" % (name, exc))

    def _reopened(self, *_args):
        """macOS asks for the main window when the app is brought forward
        with none showing. Hold-to-see brings Squint forward for its own
        window, and the main window then opened over it. Not while that is
        up or has just closed."""
        try:
            if self.xray is not None and self.xray.recently_active():
                log("dock       : reopen ignored (hold-to-see)")
                return
        except Exception:
            pass
        self.show_window()

    def _start_hotkeys(self):
        self.hotkeys = hotkey.HotkeyManager()
        # `_pressed` rather than a bare queue.put, so the log can tell a
        # shortcut that never fired from one that fired and then failed at
        # what it does. Those look identical from the outside — "nothing
        # happens" — and have nothing in common behind it.
        self.hk_snip_id = self.hotkeys.register(
            CFG["hotkey"], lambda: self._pressed("snip"))
        self.hk_clip_id = self.hotkeys.register(
            CFG["hotkey_clipboard"], lambda: self._pressed("clip"))
        # The radial menu of everyday tools (app/radial): one more
        # shortcut beside Squint's own, which stay exactly as they were.
        self.hk_radial_id = None
        self.radial_hotkey = None
        if sys.platform in ("win32", "darwin") and \
                CFG.get("radial_enabled", True):
            spec = CFG.get("hotkey_radial") or "alt+space"
            # 1.50-1.52 shipped Ctrl+Alt+Space; the quicker Alt+Space is
            # the default now, unless someone chose another on purpose.
            if spec == "ctrl+alt+space" and \
                    not CFG.get("hotkey_radial_chosen", False):
                spec = "alt+space"
            try:
                self.hk_radial_id = self.hotkeys.register(
                    spec, lambda: self._pressed("radial"))
                self.radial_hotkey = spec
            except Exception:
                log("radial     : shortcut not registered:\n%s"
                    % traceback.format_exc())
        self.hotkeys.start()
        ready = self.hotkeys.wait_ready(3.0)
        problems = [self.hotkeys.error_for(self.hk_snip_id),
                    self.hotkeys.error_for(self.hk_clip_id)]
        problems = [p for p in problems if p]
        if self.hk_radial_id is not None:
            radial_problem = self.hotkeys.error_for(self.hk_radial_id)
            if radial_problem and self.radial_hotkey != "ctrl+alt+space":
                # Taken by another app (PowerToys Run uses Alt+Space):
                # fall back to the longer one rather than have none.
                log("radial     : %s taken (%s), using ctrl+alt+space"
                    % (self.radial_hotkey, radial_problem))
                new_id, err = self.hotkeys.rebind(self.hk_radial_id,
                                                  "ctrl+alt+space")
                self.hk_radial_id = new_id
                self.radial_hotkey = "ctrl+alt+space"
                radial_problem = err
            log("radial     : %s %s" % (self.radial_hotkey,
                                        radial_problem or "ready"))
            if radial_problem:
                problems.append(radial_problem)
            try:
                from . import radial
                radial.start(self)
            except Exception:
                log("radial     : start failed:\n%s" % traceback.format_exc())
        # Written down whether or not anything went wrong, because the
        # question a log gets read for is "did the shortcut fire", and the
        # two backends fail for opposite reasons: one needs no permission
        # and can be taken by another app, the other needs Accessibility
        # and is silent without it. Which one is running was the single
        # fact missing from a log used to chase exactly this, and its
        # absence turned a two-minute answer into an afternoon.
        log("hotkey     : backend=%s ready=%s window-server=%s "
            "snip=%s (hold: see translated) clipboard=%s"
            % (getattr(self.hotkeys, "backend", "?"), ready,
               getattr(self.hotkeys, "ui_status", "?"),
               CFG["hotkey"], CFG["hotkey_clipboard"]))
        for note in getattr(self.hotkeys, "notes", []):
            log("hotkey     : %s" % note)
        # So the shortcut box in Settings can let go of them while it
        # listens. Without this it can never record the combination that is
        # already bound, because that registration eats the keystroke.
        try:
            from . import shortcut_field
            shortcut_field.HOTKEYS = self.hotkeys
        except Exception:
            pass
        self.root.after(HOTKEY_CHECK, self._watch_hotkeys)
        if problems:
            hint = hotkey.permission_hint()
            if hint:
                problems = [p + "  " + hint.split("\n")[0] for p in problems]
            log("hotkey problems: %s" % "; ".join(problems))
            self.root.after(1200, lambda: self._warn_hotkeys(problems))

    def _watch_hotkeys(self):
        """Every half minute, is the shortcut still there?

        The watcher notices its own death and restarts itself, and that is
        not enough on its own: the thing doing the noticing is a thread,
        and a thread that dies takes the only watcher of the watcher with
        it. Nothing in the app would ever find out.

        A shortcut is not a feature that may be unavailable — it is how
        this app is used, and the person pressing it has no way to tell a
        dead watcher from a dead app. So it is checked, on a timer, for as
        long as Squint is running.
        """
        try:
            if self.hotkeys is not None and self.hotkeys.check():
                log("hotkey     : the watcher had stopped — restarting it")
            for note in getattr(self.hotkeys, "notes", [])[:]:
                log("hotkey     : %s" % note)
                self.hotkeys.notes.remove(note)
        except Exception:
            pass
        try:
            self.root.after(HOTKEY_CHECK, self._watch_hotkeys)
        except Exception:
            pass

    def _pressed(self, action):
        """A shortcut arrived. Runs on the hotkey thread, so it only queues."""
        log("hotkey     : %s pressed" % action)
        self.queue.put((action, None))

    def _warn_hotkeys(self, problems):
        if self._first_run_open():
            # Same reasoning as _warn_no_tray: this fires 1.2s into
            # startup, which on a fresh install is squarely inside the
            # window somebody is still reading the wizard's first screen.
            # Showing the main window now would bury it, silently, with
            # nothing left to bring it back to the front.
            self.root.after(800, lambda: self._warn_hotkeys(problems))
            return
        if self.window is not None:
            self.window.set_hotkey_status(problems)
            self.window.show()
            self.window.segmented.select(2)
        if self.tray:
            self.tray.notify("Shortcut unavailable: %s\nPick another one in "
                             "Settings." % problems[0])

    # -- queue pump (hotkey thread -> Tk thread) -----------------------
    def _pump(self):
        try:
            while True:
                action, payload = self.queue.get_nowait()
                if action == "snip":
                    self.snip_key_pressed()
                elif action == "clip":
                    self.trigger_clipboard()
                elif action == "radial":
                    try:
                        from . import radial
                        radial.open_menu(self)
                    except Exception:
                        log("radial     : menu failed:\n%s"
                            % traceback.format_exc())
                elif action == "xray":
                    self.trigger_xray()
                elif action == "xray_frame":
                    if self.xray is not None:
                        self.xray.frame(payload)
                elif action == "show":
                    self.show_window()
                elif action == "panel":
                    self.show_panel()
                elif action == "check_done":
                    self._check_done(*payload)
                elif action == "quit":
                    self.quit()
                elif action == "toast":
                    toast, message = payload
                    if not getattr(toast, "cancelled", False):
                        toast.set(message)
                elif action == "overlay_part":
                    self._show_part(*payload)
                elif action in ("overlay", "snip_done"):
                    # A snip cancelled on the way (cancel_snip) finishes in
                    # the background: its result is kept for the same area
                    # (or handed to a snip of it that is waiting now).
                    payload = self._landing(action, payload)
                    if payload is not None:
                        if action == "overlay":
                            self._show_overlay(*payload)
                        else:
                            self._finish_snip(*payload)
                elif action == "clip_done":
                    self._finish_clip(*payload)
                elif action == "clip_inplace":
                    self._clip_in_place(*payload)
                elif action == "update_found":
                    self._announce_update(payload)
                elif action == "toolkit_ready":
                    self._toolkit_ready()
                elif action == "update_dot":
                    self._refresh_update_dot()
                del payload
        except queue.Empty:
            pass
        except Exception:
            # One bad item used to end the pump for the rest of the run.
            #
            # This loop is the only way anything reaches the app from
            # another thread — every global shortcut arrives here. The
            # reschedule sat after the try, so an exception from any
            # handler skipped it, and nothing ever queued was looked at
            # again. The window carried on working perfectly, because its
            # buttons call the same actions directly and never touch this
            # queue. Shortcuts dead, buttons fine, no error anywhere: an
            # app that looks like macOS is withholding the keystrokes.
            #
            # Restarting it is not optimism about the failure. It is that a
            # queue nobody drains is a worse outcome than a repeated
            # complaint in the log, and the complaint is now in the log.
            log("pump       : %s" % traceback.format_exc())
        finally:
            try:
                self.root.after(60, self._pump)
            except Exception:
                pass          # the window is gone; so is the app

    def _warm_reader(self):
        try:
            ocr.warm()
        except Exception:
            log(traceback.format_exc())
        # Offline translation, fetched on the first start without being
        # asked (offline_model.auto_setup); resumed on later starts until
        # it has arrived.
        try:
            from . import offline_model
            log("offline    : %s" % offline_model.auto_setup())
        except Exception:
            log(traceback.format_exc())

    # -- actions -------------------------------------------------------
    # How long the snip shortcut must be held to mean hold-to-see rather
    # than a snip. A tap is over well inside this; holding is a decision.
    HOLD_SECONDS = 0.3
    HOLD_LONG = 1.0
    HOLD_POLL_MS = 25

    def snip_key_pressed(self):
        """One shortcut, three meanings.

        Tap it: snip, when it is let go. Hold it: the whole screen
        translated in place, for as long as it is held (app/xray.py).
        Press the letter again while still holding: that view stays until
        Esc or a click.

        While a hold-to-see view is up, every press belongs to it - the
        second letter that keeps it, or the press that closes a kept one.
        """
        try:
            from . import preread
            preread.hold_off()
        except Exception:
            pass
        xray = self._xray()
        if xray is not None and (xray.win is not None or xray.opening):
            xray.press(CFG["hotkey"])
            return
        # The shortcut pressed again while a snip is still reading or
        # translating: that snip is cancelled and this press starts afresh.
        if self.busy.locked() and self.cancel_snip():
            pass
        if self.busy.locked() or getattr(self, "_deciding", False):
            return
        from . import keystate
        spec = CFG["hotkey"]
        if keystate.is_down(spec) is None or \
                keystate.modifiers_down(spec) is None:
            self.trigger_snip()        # cannot tell a hold: as it always was
            return
        self._deciding = True
        started = time.monotonic()
        # Whether this turns out to be a tap or a hold, the page in front
        # is about to be read: begin now (app/preread.py, read_now).
        try:
            from . import preread
            preread.read_now()
        except Exception:
            pass

        seen = {"down": 0, "ups": 0, "reads": 0}

        def decided(what):
            self._deciding = False
            log("hotkey     : %s after %.0fms (X read down %d of %d times)"
                % (what, 1000 * (time.monotonic() - started), seen["down"],
                   seen["reads"]))

        def let_go():
            """Whether the shortcut has been let go (macOS says so for
            certain), or None where that cannot be told."""
            try:
                released = getattr(self.hotkeys, "released", None)
                return released(self.hk_snip_id) if released else None
            except Exception:
                return None

        def watch():
            try:
                held = time.monotonic() - started
                # Where the system says when the shortcut is let go, that
                # decides: let go before HOLD_SECONDS is a snip, still held
                # then is hold-to-see. A quick tap is over before X is
                # first read, and with Ctrl and Cmd still resting on the
                # keys it was taken for a hold - the page went dark, the
                # whole page was translated, and the snip had to wait.
                gone = let_go()
                if gone is True:
                    seen["reads"] += 1
                    decided("tap")
                    self.trigger_snip()
                    return
                if gone is False:
                    seen["reads"] += 1
                    if held >= self.HOLD_SECONDS:
                        seen["down"] = seen["reads"]
                        decided("hold")
                        self.trigger_xray()
                        return
                    self.root.after(self.HOLD_POLL_MS, watch)
                    return
                key = keystate.is_down(spec)
                mods = keystate.modifiers_down(spec)
                seen["reads"] += 1
                # The letter decides. Let go of X before HOLD_SECONDS and it
                # is a snip, whether Ctrl and Alt are still held or not;
                # still down at HOLD_SECONDS and it is hold-to-see.
                #
                # But only a letter that was seen down can be seen let go.
                # On the first press on a new page, X could read as up while
                # it was held, and with Ctrl and Alt still down that was
                # taken for a tap: a snip instead of hold-to-see. So "up"
                # counts (twice running) once X has read as down, or when
                # Ctrl and Alt are up as well - the whole hand off the keys.
                if key:
                    seen["down"] += 1
                    seen["ups"] = 0
                    if held >= self.HOLD_SECONDS:
                        decided("hold")
                        self.trigger_xray()
                        return
                else:
                    seen["ups"] += 1
                    if seen["ups"] >= 2 and (seen["down"] or not mods):
                        decided("tap")
                        self.trigger_snip()
                        return
                    if held >= self.HOLD_SECONDS and mods and \
                            not seen["down"]:
                        # X never read as down, Ctrl and Alt held all along:
                        # the hand is on the keys - a hold.
                        decided("hold (X not readable)")
                        self.trigger_xray()
                        return
                self.root.after(self.HOLD_POLL_MS, watch)
            except Exception:
                self._deciding = False
                log(traceback.format_exc())
        self.root.after(self.HOLD_POLL_MS, watch)

    def _landing(self, action, payload):
        """Where a finished snip's result goes: shown (the payload, with
        the indicator it belongs to now), or kept (None)."""
        toast = payload[0]
        if not getattr(toast, "cancelled", False):
            return payload
        key = getattr(toast, "job_key", None)
        live = getattr(self, "_snip_toast", None)
        if key is not None and live is not None and \
                not getattr(live, "cancelled", False) and \
                getattr(live, "job_key", None) == key:
            return (live,) + tuple(payload[1:])
        if key is not None:
            self._ready = (key, time.monotonic(), action, payload)
            log("snip       : cancelled snip finished - kept for next time")
        return None

    def _xray(self):
        if self.xray is None:
            try:
                from .xray import XRay
                self.xray = XRay(self)
            except Exception:
                log(traceback.format_exc())
        return self.xray

    def trigger_xray(self):
        """Hold-to-see. See app/xray.py."""
        try:
            xray = self._xray()
            if xray is not None:
                xray.press(CFG["hotkey"])
        except Exception:
            log(traceback.format_exc())

    def cancel_snip(self):
        """Stop the snip that is reading or translating, from a click on
        its indicator or the shortcut pressed again. True if there was one.

        The reading or translating under way cannot be pulled back mid
        request; it is told to stop (translator.set_stop) at the next point
        it can, its result is dropped, and the app is free at once."""
        toast = getattr(self, "_snip_toast", None)
        if toast is None or getattr(toast, "cancelled", False):
            return False
        toast.cancelled = True
        self._snip_toast = None
        part = self._drop_part(toast)
        if part is not None:
            try:
                part.close()
            except Exception:
                pass
        # Not stopped: it finishes in the background and its result is kept
        # (READY_KEEP), so snipping there again is instant. It is stopped
        # only if the next snip is somewhere else (_settle_detached).
        self._detached = getattr(self, "_snip_job", None)
        try:
            toast.close()
        except Exception:
            pass
        try:
            self.busy.release()
        except RuntimeError:
            pass
        log("snip       : cancelled - finishing in the background")
        return True

    def _watch_esc(self, toast):
        """Esc cancels a snip while it reads or translates, whichever app
        has the keyboard: the key is looked at, not waited for. It has to
        be seen up first, so the Esc that closed something else a moment
        ago does not count."""
        from . import keystate
        seen_up = {"yes": False}

        def tick():
            if getattr(toast, "cancelled", False) or \
                    getattr(self, "_snip_toast", None) is not toast:
                return
            down = keystate.is_down("esc")
            if down is None:
                return                   # cannot be told here
            if not down:
                seen_up["yes"] = True
            elif seen_up["yes"]:
                self.cancel_snip()
                return
            self.root.after(40, tick)
        try:
            self.root.after(40, tick)
        except Exception:
            pass

    def _reuse_cancelled(self, toast):
        """True if this snip is taken care of by one cancelled before: its
        result is shown now, or it is still working and will show there."""
        key = getattr(toast, "job_key", None)
        if key is None:
            return False
        ready = getattr(self, "_ready", None)
        if ready is not None and ready[0] == key and \
                time.monotonic() - ready[1] < READY_KEEP:
            self._ready = None
            _key, _at, action, payload = ready
            log("snip       : shown from the snip cancelled before")
            self.queue.put((action, (toast,) + tuple(payload[1:])))
            return True
        job = getattr(self, "_detached", None)
        if job is not None and not job.finished and job.key == key:
            job.toast = toast
            self._snip_job = job
            self._detached = None
            log("snip       : picked up the snip cancelled before")
            return True
        return False

    def _settle_detached(self, origin, image, scale):
        """Events a new snip should wait for before working: a cancelled
        snip still busy with much the same area, or the page being prepared
        ahead on this screen. A cancelled one somewhere else is stopped."""
        waits = []
        here = (float(origin[0]), float(origin[1]),
                image.width / scale, image.height / scale)
        # Nothing is waited for. A new snip waited for a cancelled one of
        # much the same area, or for the page being prepared for
        # hold-to-see, to share its work - and waited 34 and 45 seconds when
        # that work was slow. Whatever else is under way is stopped, and
        # this snip does its own work.
        job = getattr(self, "_detached", None)
        if job is not None and not job.finished:
            job.stop.set()
            self._detached = None
            log("snip       : stopped the snip cancelled before")
        try:
            xray = self.xray
            prep = getattr(xray, "prep_state", None) if xray else None
            if prep and not prep["done"].is_set() and \
                    prep.get("stop") is not None:
                prep["stop"].set()
                log("snip       : stopped preparing a page")
        except Exception:
            pass
        return waits

    def _prepare_page(self):
        """See XRay.prepare."""
        try:
            xray = self._xray()
            if xray is not None and not self.busy.locked():
                xray.prepare()
        except Exception:
            log(traceback.format_exc())

    def trigger_snip(self):
        if not self.busy.acquire(blocking=False):
            return
        try:
            ResultPopup.close_all()
            OverlayWindow.close_all()
            if self.window is not None and self.window.winfo_viewable():
                self.window.withdraw()
            # One path, not two.
            #
            # The window being open took the slow route — withdraw, let the
            # toolkit settle, build the overlay 120ms later — and the window
            # being hidden took the fast one, straight into the overlay. So
            # clicking the button worked and pressing the shortcut, which is
            # the case where the window is always hidden, did not: asking
            # macOS to bring the app forward is a request to the window
            # server, not something that has happened by the next line, and
            # a borderless always-on-top window built before it lands is
            # built behind everything and never seen.
            #
            # The two routes existed for no reason anybody wrote down. The
            # one that worked is now the only one.
            log("snip       : %s" % platform_util.become_foreground_app())
            self.root.update_idletasks()
            self.root.after(120, self._do_snip)
        except Exception:
            self.busy.release()
            log(traceback.format_exc())

    def _do_snip(self):
        image, origin, scale = None, (0, 0), 1.0
        try:
            # Bring the app forward FIRST. The shortcut fires while another
            # app is frontmost, and macOS delivers key events only to the
            # frontmost application — so without this the snip window appears
            # but Esc goes to the browser underneath, and there is no way to
            # cancel. The binding was never the problem; the focus was.
            platform_util.become_foreground_app()
            # Hy-MT2 loads while the area is dragged, not after.
            try:
                from . import offline_model, profile
                # Under Automatic it runs beside the online engines, so
                # it is wanted loaded there too.
                if profile.current() in (profile.AUTO, profile.LOCAL):
                    offline_model.warm()
            except Exception:
                pass
            picker = snip.SnipOverlay(self.root)
            image = picker.select()
            origin = picker.origin
            scale = getattr(picker, "scale_used", 1.0) or 1.0
        except Exception:
            log(traceback.format_exc())
        if image is None:
            self.busy.release()
            # Dismissed without a box (Esc, or an accidental press): the
            # page in front is read and translated anyway, quietly and on
            # this computer only, so the next snip or hold there is quick.
            self.root.after(350, self._prepare_page)
            return
        self._snip_area(image, origin, scale)

    def _snip_area(self, image, origin, scale, started_at=None):
        """Read, translate and draw over `image`, which is the part of the
        screen at `origin` - a snipped box, or the text found for
        translate-selection (app/inplace.py). The caller holds self.busy."""
        # Over the area that was snipped, where the translation will appear,
        # rather than a small pill by the cursor that was easy to miss.
        from .ui_result import working_indicator
        s = scale or 1.0
        toast = working_indicator(self.root, origin[0], origin[1],
                                  image.width / s, image.height / s,
                                  "Reading text…", palette=self.palette())
        stop = threading.Event()
        toast.cancelled = False
        try:
            from .xray import _fingerprint
            toast.job_key = (_fingerprint(image), int(round(origin[0])),
                             int(round(origin[1])), CFG["target_lang"])
        except Exception:
            toast.job_key = None
        self._snip_toast, self._snip_stop = toast, stop
        try:
            toast.on_click(self.cancel_snip)
        except Exception:
            pass
        self._watch_esc(toast)
        # The same area snipped again after a cancel: its translation, if
        # it has finished since, or the snip still working on it.
        if self._reuse_cancelled(toast):
            return
        wait_for = self._settle_detached(origin, image, s)
        job = _SnipJob(toast.job_key, toast, stop)
        job.area = (float(origin[0]), float(origin[1]),
                    image.width / s, image.height / s)
        self._snip_job = job
        target = CFG["target_lang"]
        use_overlay = bool(CFG.get("overlay_mode", True))
        # If the user has named the source language, OCR should be told.
        # Vision reads Cyrillic as Latin lookalikes when left to prefer
        # English, and returns them at high confidence.
        source = ""
        try:
            from .langs import code_for_name
            chosen = str(CFG.get("source_lang_name", "") or "")
            if chosen and not chosen.lower().startswith("detect"):
                source = code_for_name(chosen) or ""
        except Exception:
            source = ""

        import time as _t0
        snip_done_at = started_at or _t0.time()

        def work():
            translator.set_stop(stop)
            for event in wait_for:
                # A cancelled snip of much the same area, or the page being
                # prepared ahead: what it reads and translates is used
                # here, instead of doing the same work twice at once.
                event.wait(SETTLE_WAIT)
            try:
                if use_overlay:
                    # Where the time goes, one line per snip. Asking for a
                    # timing tool to be run is a round trip; this is in
                    # every log already.
                    import time as _time
                    started = _time.time()
                    # Already read while you were looking at the page, if
                    # read-ahead is on and the screen there is unchanged
                    # (app/preread.py); otherwise read now, as always.
                    # A snip reads its own area, always. It used to take
                    # the reading made when the shortcut was pressed, or
                    # the last snip's, when the screen there looked the
                    # same - half a second saved, and whatever that
                    # reading had missed (a paragraph passed over at the
                    # size of a whole window) left untranslated on the
                    # page. Reading a snip takes well under a second.
                    reused = None
                    if reused is not None:
                        lines, lang = reused[0], (reused[1].lang or "")
                        log("read-ahead : snip used %d lines already read"
                            % len(lines))
                    else:
                        lines, lang = ocr.image_to_lines(image,
                                                         source=source)
                    read_ms = 1000 * (_time.time() - started)
                    try:
                        from . import preread
                        preread.remember_snip(image, origin, scale, lines,
                                              lang)
                    except Exception:
                        pass
                    if stop.is_set():
                        return
                    if lines:
                        self.queue.put(("toast", (job.toast, "Translating…")))
                        from . import http_pool
                        # The size follows the size of the capture, not a
                        # setting. One sentence grabbed off a page wants to
                        # be readable where it sits; a whole page wants to
                        # still look like the page, and is read by zooming
                        # into it. A single preference cannot be both, and
                        # as a floor it did the opposite of what it said —
                        # raising it stopped the text fitting and cut the
                        # remainder off.
                        points = max(1, image.width / (scale or 1.0))
                        # And on Windows, by the scale the display itself
                        # is drawn at. "How much of the screen was
                        # grabbed" has to mean the same thing on every
                        # monitor, and it does not measured in pixels: a
                        # 4K display set to 150% draws the same document
                        # half again as wide, so a modest selection on it
                        # counted as a whole page and was set at the size
                        # a whole page gets. macOS answers zero here and
                        # is handled by `scale` above.
                        try:
                            percent = platform_util.monitor_scaling(
                                int(origin[0]), int(origin[1]))
                            if percent:
                                points = max(1, points * 100.0 / percent)
                        except Exception:
                            pass
                        _floor_px, floor = overlay.size_policy(points)
                        floor = int(round(floor * (scale or 1.0)))
                        pad = overlay.MARK_PAD
                        placed = (origin[0] - pad, origin[1] - pad)
                        first = {"at": None}

                        def shown(partial, _tall):
                            # The page as it fills in, top left first.
                            if first["at"] is None:
                                first["at"] = _time.time()
                            self.queue.put(("overlay_part", (
                                job, image, partial, placed, scale)))
                        started = _time.time()
                        texts, blocks, tall = overlay.progressive(
                            image, lines, translator, target,
                            source or "auto", floor, shown=shown)
                        detail = ""
                        if reused is None:
                            detail = ocr.reading_detail()
                        log("timing     : read %.0fms (%d lines, %dx%d, "
                            "read as %s%s) | translate %.0fms via %s | "
                            "network %s"
                            % (read_ms, len(lines), image.width,
                               image.height, lang or "?",
                               ", " + detail if detail else "",
                               1000 * (_time.time() - started),
                               CFG.get("last_backend", "") or "?",
                               http_pool.POOL.summary()))
                        # A reference number the engine dropped is the one
                        # mistake the reader cannot catch: they cannot read
                        # the sentence it went missing from. Say so here,
                        # where a report of "the number is wrong" can be
                        # answered without guessing.
                        try:
                            log("overlay    : %d lines as %d paragraphs (%s)"
                                % (len(lines), len(overlay.last_groups),
                                   " ".join(str(n) for n in
                                            overlay.last_groups)))
                        except Exception:
                            pass
                        if overlay.lost_identifiers:
                            log("overlay    : the engine dropped %s"
                                % ", ".join(overlay.lost_identifiers[:6]))
                        log("timing     : first words shown after %s | from "
                            "release of the mouse to the translation %.0fms"
                            % ("%.0fms" % (1000 * (first["at"] - snip_done_at))
                               if first["at"] else "the end",
                               1000 * (_time.time() - snip_done_at)))
                        try:
                            from . import budget
                            log("budget     : " + budget.line(
                                read_ms,
                                1000 * (first["at"] - snip_done_at)
                                if first["at"] else None,
                                1000 * (_time.time() - snip_done_at)))
                        except Exception:
                            pass
                        # Lines, not blocks: a paragraph is one block and
                        # several lines, and the check below is against the
                        # number of lines that were read.
                        drawn = overlay.lines_covered(blocks)
                        # An overlay that covers most of what was read is
                        # a translation of the page. One that covers three
                        # lines out of twenty is a page with three lines
                        # changed on it, which reads as a finished job
                        # badly done — the user cannot tell the untouched
                        # lines from lines the app decided to leave. When
                        # too little came back, the card is the honest
                        # answer: it puts the translation beside the
                        # original instead of pretending to replace it.
                        # Figures and addresses are left as they are on
                        # purpose (overlay.held_back), so they are not
                        # lines the overlay failed to cover: a table of
                        # numbers under a row of headings is all
                        # translated when the headings are.
                        try:
                            kept = overlay.held_back(lines)
                        except Exception:
                            kept = set()
                        wanted = sum(1 for i, ln in enumerate(lines)
                                     if str(ln.get("text", "")).strip()
                                     and i not in kept)
                        # Shown over the page unless most of what is
                        # words came back as it went: a page of figures,
                        # units and names left as they are is translated,
                        # and was sent to the card for it ("25-40PSI").
                        left, judged = overlay.left_as_they_were(lines)
                        if drawn and left <= 0.5 * max(1, judged):
                            plain = "\n".join(t for t in texts if t.strip())

                            again = zoomer(image, lines, texts, target,
                                           floor)
                            # The overlay is padded so the mark has room
                            # round the text; the window moves back by
                            # the same amount or it stops lining up with
                            # what it replaced.
                            pad = overlay.MARK_PAD
                            placed = (origin[0] - pad, origin[1] - pad)
                            self.queue.put(("overlay", (
                                job.toast, (image, blocks, tall), placed, plain,
                                scale, again,
                                {"image": image, "lines": lines,
                                 "texts": texts, "floor": floor,
                                 "target": target, "placed": placed,
                                 "scale": scale,
                                 "lost": list(overlay.last_lost)})))
                            return
                    # Nothing positioned to draw — fall through to the card.
                text, lang = ocr.image_to_text(image, source=source)
                # The reader may have something to say about why this went
                # badly — on Windows, most often that the language on
                # screen has no recognition pack installed. Saying "no text
                # found" instead would send the user looking in the wrong
                # place entirely.
                note = ocr.reading_note()
                if not text.strip():
                    self.queue.put(("snip_done", (
                        job.toast, None, "",
                        note or "No text found in that selection.")))
                    return
                self.queue.put(("toast", (job.toast, "Translating…")))
                out = translator.translate_best(text, target=target,
                                                source=source or "auto")
                meta = "%s → %s" % (lang.split("+")[0], name_for(target))
                if note:
                    meta += "  ·  " + note
                self.queue.put(("snip_done", (job.toast, out, text, meta)))
            except translator.Cancelled:
                log("snip       : stopped after cancel")
            except Exception as exc:
                if stop.is_set():
                    return
                log(traceback.format_exc())
                self.queue.put(("snip_done", (job.toast, None, "", str(exc))))
            finally:
                translator.set_stop(None)
                job.finished = True
                job.done.set()

        threading.Thread(target=work, daemon=True).start()

    def _show_part(self, job, image, blocks, placed, scale):
        """A snip's page as far as it is translated, drawn in the window
        the finished page will be shown in (see overlay.progressive)."""
        toast = job.toast
        if getattr(toast, "cancelled", False) or not blocks:
            return
        if toast is not getattr(self, "_snip_toast", None):
            return
        win = getattr(toast, "partial_window", None)
        try:
            if win is not None and win.winfo_exists():
                win.show_blocks(blocks)
                return
        except Exception:
            pass
        try:
            win = OverlayWindow(
                self.root, image, placed[0], placed[1], on_copy=None,
                rerender=None, shrink=scale if scale and scale > 1.01 else 1.0,
                blocks=blocks, height=None, notice="",
                engine=translator.engine_label())
            win.on_close = lambda: self._part_closed(toast)
            toast.partial_window = win
        except Exception:
            log(traceback.format_exc())

    def _part_closed(self, toast):
        """The half-finished page was closed (Esc, a click away): that is
        cancelling the snip."""
        toast.partial_window = None
        if toast is getattr(self, "_snip_toast", None):
            self.cancel_snip()

    @staticmethod
    def _drop_part(toast):
        win = getattr(toast, "partial_window", None) if toast else None
        if win is None:
            return None
        toast.partial_window = None
        win.on_close = None
        return win

    def _show_overlay(self, toast, image, origin, plain_text, scale=1.0,
                      rerender=None, page=None):
        part = self._drop_part(toast)
        if part is not None:
            page_ = page or {}
            try:
                fits = isinstance(image, tuple) and part.winfo_exists() \
                    and not page_.get("lost") \
                    and (image[2] or 0) <= image[0].height
            except Exception:
                fits = False
            if fits:
                # The window that showed the page filling in shows it
                # finished: no second window, no flicker.
                if toast is getattr(self, "_snip_toast", None):
                    self._snip_toast = None
                toast.close()
                try:
                    part.finish(image[1], on_copy=plain_text,
                                rerender=rerender,
                                engine=translator.engine_label())
                    if CFG["auto_copy"] and plain_text:
                        self.root.clipboard_clear()
                        self.root.clipboard_append(plain_text)
                    if page_.get("lines"):
                        self._remember(page_, image[1], image[2], image[0],
                                       origin, plain_text)
                except Exception:
                    log(traceback.format_exc())
                finally:
                    try:
                        self.busy.release()
                    except RuntimeError:
                        pass
                return
            try:
                part.close()
            except Exception:
                pass
        if toast is not None:
            if toast is getattr(self, "_snip_toast", None):
                self._snip_toast = None
            toast.close()
        page = page or {}
        blocks = tall = None
        if isinstance(image, tuple):
            # A layout rather than a finished picture: the text is drawn as
            # canvas items at the display's own resolution instead of being
            # baked into a bitmap that has to be scaled twice to get there.
            image, blocks, tall = image
        try:
            if blocks is None and scale and scale > 1.01:
                # The bitmap path still has to be shrunk by hand: windows
                # are placed in logical points, and a picture made at
                # capture resolution is twice the size it should be.
                from PIL import Image as _Image
                image = image.resize(
                    (max(1, int(image.width / scale)),
                     max(1, int(image.height / scale))), _Image.LANCZOS)
            if CFG["auto_copy"] and plain_text:
                try:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(plain_text)
                    self.root.update()
                except Exception:
                    pass
            lost = list(page.get("lost") or ())
            OverlayWindow(
                self.root, image, origin[0], origin[1],
                on_copy=plain_text, rerender=rerender,
                shrink=scale if scale and scale > 1.01 else 1.0,
                blocks=blocks, height=tall,
                notice=self._lost_notice(lost),
                engine=translator.engine_label())
            if page.get("lines"):
                self._remember(page, blocks, tall, image, origin, plain_text)
        except Exception:
            log(traceback.format_exc())
        finally:
            try:
                self.busy.release()
            except RuntimeError:
                pass

    # -- the last few translations --------------------------------------
    def _remember(self, page, blocks, tall, image, origin, plain_text):
        """Keep a finished translation so it can be opened again.

        Everything needed is already in hand at this point: the picture,
        the lines read out of it, the laid-out blocks. Keeping them costs
        nothing to produce and saves finding the document a second time.
        """
        try:
            words = " ".join(str(plain_text or "").split())
            label = (words[:34] + "…") if len(words) > 35 else words
            entry = {"page": page, "blocks": blocks, "tall": tall,
                     "image": image, "origin": origin,
                     "plain": plain_text or "",
                     "label": label or "(no text)",
                     "language": name_for(page.get("target")
                                          or CFG["target_lang"])}
            self.recent.insert(0, entry)
            del self.recent[RECENT_KEEP:]
            self._show_recent()
        except Exception:
            log(traceback.format_exc())

    def _show_recent(self):
        if self.window is None:
            return
        try:
            self.window.show_recent(
                [("%s  ·  %s" % (item["label"], item["language"]), index)
                 for index, item in enumerate(self.recent)],
                self.reopen_recent)
        except Exception:
            log(traceback.format_exc())

    def reopen_recent(self, index):
        """Put a kept translation back on screen where it came from."""
        try:
            item = self.recent[int(index)]
        except Exception:
            return
        ResultPopup.close_all()
        OverlayWindow.close_all()
        if self.window is not None and self.window.winfo_viewable():
            self.window.withdraw()
        page = item["page"]
        again = None
        try:
            again = zoomer(page["image"], page["lines"], page["texts"],
                           page["target"], page["floor"])
        except Exception:
            again = None
        self._show_overlay(None, (item["image"], item["blocks"],
                                  item["tall"]),
                           item["origin"], item["plain"],
                           page.get("scale", 1.0), again, page)

    @staticmethod
    def _lost_notice(lost):
        """What to say when the engine dropped a code, or nothing.

        Written on the overlay rather than only in the log, which is the
        one place nobody looks. A reference number missing from an
        otherwise fluent sentence is the single mistake the reader cannot
        catch — they cannot check it against a sentence they cannot read.
        """
        if not lost:
            return ""
        shown = ", ".join(lost[:2])
        if len(lost) > 2:
            shown += " and %d more" % (len(lost) - 2)
        return ("%d code could not be placed: %s" % (len(lost), shown)
                if len(lost) == 1
                else "%d codes could not be placed: %s" % (len(lost), shown))

    def _finish_snip(self, toast, translated, original, meta):
        part = self._drop_part(toast)
        if part is not None:
            try:
                part.close()
            except Exception:
                pass
        if toast is getattr(self, "_snip_toast", None):
            self._snip_toast = None
        toast.close()
        try:
            if translated is None:
                self._show_problem(meta or "Nothing to translate.")
                return
            if CFG["auto_copy"]:
                try:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(translated)
                    self.root.update()
                except Exception:
                    pass
            ResultPopup(self.root, translated, original, meta,
                        show_original=CFG["show_original"],
                        font_size=int(CFG.get("popup_font_size", 12)),
                        palette=self.palette(),
                        engine=translator.engine_label())
        finally:
            try:
                self.busy.release()
            except RuntimeError:
                pass

    def trigger_clipboard(self, given=None):
        """Translate the selected text — copying it is the app's job.

        This used to translate whatever was already on the clipboard,
        which made reading one sentence a three-step operation: select,
        Ctrl+C, shortcut. Forget the middle step and it said "copy
        something first", which is true and useless. Now it presses Ctrl+C
        for you.

        Not root.clipboard_get() anywhere here: that asks Windows for
        CF_TEXT, the ANSI format, and Chinese is not in it.
        """
        from . import clipboard as clipboard_mod, selection
        # Nothing may appear on screen before the copy on macOS.
        #
        # This is the whole bug, and it is not about permission. Showing a
        # window brings the application to the front — Tk maps the toplevel
        # and macOS activates the process that owns it. The copy is then
        # sent to the app that is frontmost, which by that point is Squint,
        # and Squint's own toast has nothing selected in it. The user's
        # browser, one window behind, never sees the keystroke.
        #
        # It looked exactly like a permission failure: ⌘C by hand then the
        # shortcut worked, the shortcut alone never did, and Accessibility
        # was the obvious suspect. It survived being granted.
        #
        # The toast was deliberate — waiting for the modifiers to come up
        # and then for the clipboard to change takes a moment, and a
        # shortcut that does nothing visible reads as one that did not
        # work. That is a real cost and it is the smaller one: on macOS the
        # toast now goes up after the text is in hand, for the translation,
        # which is the slower half anyway.
        quiet_first = sys.platform == "darwin"
        # Who was in front before anything of ours appears — see
        # _keep_main_window_back.
        self._front_before_clip = platform_util.frontmost_app()
        # The screen as it is, before anything of Squint's is on it: where
        # the selected text is, to draw its translation over it.
        shot = None
        if CFG.get("clip_in_place", False):
            try:
                from . import inplace
                shot = inplace.grab()
            except Exception:
                shot = None
        toast = None
        if not quiet_first:
            toast = StatusToast(self.root, "Reading selection…",
                                palette=self.palette())
            self.root.update_idletasks()

        before = clipboard_mod.get_text(self.root)
        restore = None
        # `given`: the selected text, already known (the icon beside a
        # selection on a Mac, app/select_icon.py). Nothing is copied.
        blocked = False if given else not selection.permitted()
        if blocked and not self._told_permission:
            # Say it here, once, and stop — rather than quietly translating
            # the clipboard and leaving the explanation to a notification.
            #
            # The first version put this in a tray balloon, which on macOS
            # arrives through pystray and, on the Mac this was reported
            # from, arrives nowhere at all. So the user pressed the
            # shortcut over a German paragraph, got back a GitHub URL
            # correctly labelled "clipboard", and was none the wiser about
            # why. The card is where they are already looking.
            #
            # request_permission also makes macOS add Squint to the
            # Accessibility list. Until something asks, there is no entry
            # to switch on, and the instruction "switch on the entry for
            # Squint" is about a row that does not exist.
            self._told_permission = True
            if toast is not None:
                toast.close()
            selection.request_permission()
            self._show_problem(selection.PERMISSION_HELP)
            return
        if blocked:
            # macOS refuses synthetic keystrokes to an app that has not been
            # ticked under Accessibility, and refuses them silently: the
            # keystroke never arrives and nothing reports an error. Trying
            # anyway would waste a second and end up here regardless.
            content = None
        else:
            content = given or selection.grab(self.root, previous=before)
        # One line saying which way this went, because the failures here
        # are all silent by nature: macOS refuses a synthetic keystroke
        # without a word, and falling back to whatever was on the clipboard
        # produces a confident translation of the wrong text. Reading a
        # report of "it translated something else" without this means
        # guessing between four different causes.
        log("clipboard  : permitted=%s copied=%s before=%d after=%d front=%s"
            % (not blocked, selection.copy_was_observed(),
               len(before or ""), len(content or ""),
               platform_util.frontmost_app() or "n/a"))

        # What the clipboard is now, to tell next time whether anything new
        # was put on it in between (see the fallback below).
        try:
            seen_now = clipboard_mod.sequence()
        except Exception:
            seen_now = None
        seen_before = getattr(self, "_clip_seen", None)
        if content:
            source = "selection"
            log("clipboard  : using the selection")
            # The user's own clipboard was not theirs to take. Put it back,
            # unless the app is about to fill it with the translation.
            if not CFG["auto_copy"] and before and not given:
                restore = before
        else:
            # Nothing was selected, or the window would not copy, or the OS
            # would not let us ask. Fall back to what was already there —
            # still the right answer when someone has genuinely copied
            # something first — but say so. Calling it the selection is how
            # this shortcut came to return the same stale text over and over
            # while claiming each time to have read the screen.
            content = before
            source = "clipboard"
            log("clipboard  : the copy did not land — falling back to what "
                "was already on the clipboard, which is very likely not "
                "what was on screen")
            # Say plainly that this is not what was on screen.
            #
            # The label was already honest — "clipboard" where a working
            # one says "selection" — and honest was not enough. It is one
            # quiet word on a card that otherwise looks exactly like a
            # result, and what the reader sees is fluent English about
            # something they did not select. Where the platform can tell
            # us the copy definitely did not happen, the card says so.
            if selection.copy_was_observed() is False:
                source = "old clipboard (copy failed)"
            # Nothing new on the clipboard since the last time this shortcut
            # was pressed: it is the text from before, not a copy made by
            # hand for this. Translating it put an earlier paragraph in the
            # card as if it were the one just selected. Say so instead.
            stale = clip_is_stale(content, seen_now, seen_before,
                                  getattr(self, "_clip_text_seen", ""))
            if stale:
                if toast is not None:
                    toast.close()
                self._clip_seen = seen_now
                self._show_problem(
                    "Could not copy the selected text, and the clipboard "
                    "still holds what was translated before. Select the "
                    "text again and press the shortcut - or copy it "
                    "yourself first (Ctrl+C / Cmd+C), then press it.")
                return
            # Except when the clipboard is our own previous answer, which
            # with auto-copy on is exactly what it is. Translating that
            # returns it unchanged, so the user selects a new sentence,
            # presses the shortcut, and is shown the answer to the last
            # one — word for word, in a card that looks like it worked.
            # The "clipboard" label is the only clue and nobody reads a
            # label on a result that appears to be a result.
            if (content and getattr(self, "_last_put_on_clipboard", None)
                    and content.strip() == self._last_put_on_clipboard.strip()):
                if toast is not None:
                    toast.close()
                self._show_problem(
                    "Could not copy the selected text in time, so this is "
                    "still your previous translation rather than a new "
                    "one. Try again — select the text and press the "
                    "shortcut, letting go of the keys as you press it.")
                return

        self._clip_seen = seen_now
        self._clip_text_seen = content or ""
        if not content.strip():
            if toast is not None:
                toast.close()
            if blocked:
                self._show_problem(selection.PERMISSION_HELP)
            else:
                self._show_problem(
                    "Nothing to translate. Select some text, then press the "
                    "shortcut — Squint copies it for you.")
            return
        if restore:
            def put_back():
                clipboard_mod.set_text(self.root, restore)
                self._note_clip_seen()
            self.root.after(1200, put_back)
        # The snip's pill, with the copied text being scanned under it.
        # The small "Reading selection…" pill (Windows) makes way for it.
        getattr(self, "_shield_main_window", lambda: None)()
        try:
            from .ui_result import ClipScanToast
            scan = ClipScanToast(self.root, content, "Translating…",
                                 palette=self.palette())
        except Exception:
            scan = None
        if scan is not None:
            if toast is not None:
                toast.close()
            toast = scan
        elif toast is None:
            toast = StatusToast(self.root, "Translating…",
                                palette=self.palette())
        else:
            toast.set("Translating…")
        self.root.update_idletasks()
        self._keep_main_window_back()
        target = CFG["target_lang"]

        # The lines a document wrapped are joined back into paragraphs
        # first. Text copied out of a PDF or a page of a book carries a
        # break at the end of every *rendered* line, and handing those to
        # an engine gives it a paragraph pre-chopped into fragments — what
        # comes back is chopped in the same places, and those places no
        # longer fall between words: "Our dis / hes may contain". The
        # reading path has always done this; this one never did, which is
        # why one looked broken and the other did not.
        try:
            from . import selection as _selection
            content = _selection.unwrap(content)
        except Exception:
            pass

        import time as _tc
        asked_at = _tc.time()

        def work():
            # Drawn over the selected text itself, as a snip is, where the
            # text can be found on screen (app/inplace.py); the card only
            # where it cannot.
            if shot is not None:
                try:
                    from . import inplace
                    found = inplace.locate(content, shot)
                except Exception:
                    log(traceback.format_exc())
                    found = None
                log("clipboard  : %s" % ("found on screen - drawn in place"
                                         if found else
                                         "not found on screen - the card"))
                if found is not None:
                    self.queue.put(("clip_inplace", (toast, found,
                                                     asked_at)))
                    return
            try:
                out = translator.translate_best(content, target=target)
                self.queue.put(("clip_done", (
                    toast, out, content,
                    "%s → %s" % (source, name_for(target)))))
            except Exception as exc:
                log(traceback.format_exc())
                self.queue.put(("clip_done", (toast, None, "", str(exc))))

        threading.Thread(target=work, daemon=True).start()

    def _clip_in_place(self, toast, found, asked_at):
        """Translate-selection's text, found on screen: handled as a snip of
        that area. The card if a snip is already under way."""
        image, origin, scale = found
        try:
            toast.close()
        except Exception:
            pass
        if not self.busy.acquire(blocking=False):
            log("clipboard  : busy - not drawn in place")
            return
        try:
            ResultPopup.close_all()
            OverlayWindow.close_all()
            self._snip_area(image, origin, scale, started_at=asked_at)
        except Exception:
            log(traceback.format_exc())
            try:
                self.busy.release()
            except RuntimeError:
                pass

    def _finish_clip(self, toast, translated, original, meta):
        toast.close()
        if translated is None:
            self._show_problem(meta)
            return
        if CFG["auto_copy"]:
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(translated)
                self.root.update()
                # Remember it. With auto-copy on, our own last answer is
                # what the clipboard holds, so a failed copy falls back
                # onto it — see the guard in _do_clip.
                self._last_put_on_clipboard = translated
                self._note_clip_seen()
            except Exception:
                pass
        log("clipboard  : showing the card (%s)" % self._open_windows())
        getattr(self, "_shield_main_window", lambda: None)()
        ResultPopup(self.root, translated, original, meta,
                    show_original=CFG["show_original"],
                    font_size=int(CFG.get("popup_font_size", 12)),
                    palette=self.palette(),
                    engine=translator.engine_label())
        self._keep_main_window_back()

    def _note_clip_seen(self):
        """What Squint itself just put on the clipboard is not something
        copied by hand: a failed copy next time must not fall back to it."""
        try:
            from . import clipboard as clipboard_mod
            self._clip_seen = clipboard_mod.sequence()
            self._clip_text_seen = clipboard_mod.get_text(self.root) or ""
        except Exception:
            pass

    def _keep_main_window_back(self):
        """On macOS, leave the main window where it was.

        Showing the card maps a window, macOS then activates the app that
        owns it, and activating an app brings every one of its windows
        forward — so Squint's own window, left open behind the browser,
        jumped in front of the page with the card on top of it. Every
        Ctrl+Cmd+C, whatever the engine; never on Windows, which raises
        one window rather than an application.

        Only when somebody else was in front when the shortcut was
        pressed. If Squint was, its window is where they were working.
        """
        if sys.platform != "darwin":
            return
        front = str(getattr(self, "_front_before_clip", "") or "").lower()
        if not front or front in ("squint", "python", "python3"):
            return
        window = getattr(self, "window", None)

        def lower():
            try:
                if window is not None and window.winfo_viewable():
                    window.lower()
            except Exception:
                pass
        # Now and once more after macOS has finished activating, which
        # happens on its own schedule rather than inside this call.
        lower()
        for delay in (60, 250):
            try:
                self.root.after(delay, lower)
            except Exception:
                pass
        # Visible again once it is safely behind — see _shield_main_window.
        unshield = getattr(self, "_unshield_main_window", None)
        if unshield is not None:
            try:
                self.root.after(450, unshield)
            except Exception:
                unshield()

    def _shield_main_window(self):
        """Make the main window invisible for the moment a card appears.

        Lowering it afterwards (above) was not enough: macOS brings every
        window of the app forward when one of them is shown, and the main
        window was on screen for a frame or two before it was lowered — a
        flash of the whole app over the page on every Ctrl+Cmd+C. Made
        fully transparent first, it is brought forward, lowered and shown
        again without ever being seen.
        """
        if sys.platform != "darwin":
            return
        front = str(getattr(self, "_front_before_clip", "") or "").lower()
        if not front or front in ("squint", "python", "python3"):
            return
        window = getattr(self, "window", None)
        try:
            if window is None or not window.winfo_viewable():
                return
            if getattr(self, "_shield_alpha", None) is None:
                self._shield_alpha = float(window.attributes("-alpha") or 1.0)
            window.attributes("-alpha", 0.0)
        except Exception:
            self._shield_alpha = None

    def _unshield_main_window(self):
        alpha = getattr(self, "_shield_alpha", None)
        if alpha is None:
            return
        self._shield_alpha = None
        try:
            window = self.window
            window.lower()
            window.attributes("-alpha", alpha)
        except Exception:
            pass

    def _open_windows(self):
        """What is on screen right now, for the log.

        The report that started this was a shortcut appearing to open two
        windows at once. Nothing in the code obviously does that, and
        without a record of what actually opened there is no way to tell a
        second window from a card that looked like one.
        """
        try:
            from .ui_result import OverlayWindow, ResultPopup
            report = "overlays=%d cards=%d main=%s" % (
                len(OverlayWindow._open), len(ResultPopup._open),
                bool(self.window is not None
                     and self.window.winfo_viewable()))
            # And who the OS thinks is in front. Without it, a report of
            # "the app comes up on top" cannot be told from a report about
            # the working pill, and the two need opposite fixes.
            front = platform_util.frontmost_app()
            if front:
                report += " front=%s" % front
            return report
        except Exception:
            return "unknown"

    def _show_problem(self, message):
        """Surface a failure where the user is actually looking.

        A tray balloon is easy to miss and disappears; after pressing a
        shortcut and seeing nothing, "it does not work" is the reasonable
        conclusion. The card appears at the cursor like a result would.
        """
        try:
            ResultPopup(self.root, message, "", "Could not translate",
                        show_original=False,
                        font_size=int(CFG.get("popup_font_size", 12)),
                        palette=self.palette(), kind="error")
        except Exception:
            log(traceback.format_exc())
            self.tray and self.tray.notify(message)

    # -- settings ------------------------------------------------------
    def set_language(self, code):
        CFG.set("target_lang", code)
        if self.window is not None:
            self.root.after(0, self.window.sync_language)
        self.refresh_tray()

    def refresh_tray(self):
        if self.tray:
            self.tray.refresh()

    def request_restart_for_theme(self):
        """Change the window's scheme.

        It used to build a second window and throw the first away, which
        is why light and dark blinked: a new window is new to the system
        too — it appears, it takes focus, and no amount of fading one
        into the other hides the fact that there are two of them. The
        window now rebuilds its own contents in place and dims while it
        does it. See MainWindow.restyle.
        """
        try:
            window = self.window
            if window is None:
                return
            window.restyle()
            self._palette = window.palette
            if self.tray is None:
                window.protocol("WM_DELETE_WINDOW", self.quit)
        except Exception:
            log("theme reload failed:\n%s" % traceback.format_exc())

    def apply_hotkeys(self, snip_spec, clip_spec, xray_spec=None):
        messages = []
        ok = True
        # Said before the result, because it is not a failure: the shortcut
        # registers fine and then loses to whichever app is in front. That
        # produces a shortcut which works everywhere except the program the
        # user was reading, which is the most confusing way for one to be
        # broken and looks like the app rather than the collision.
        warnings = [note for note in
                    (hotkey.risky(snip_spec), hotkey.risky(clip_spec))
                    if note]
        if snip_spec and snip_spec != CFG["hotkey"]:
            new_id, err = self.hotkeys.rebind(self.hk_snip_id, snip_spec)
            self.hk_snip_id = new_id
            if err:
                ok = False
                messages.append(err)
            else:
                CFG.set("hotkey", snip_spec)
        if clip_spec and clip_spec != CFG["hotkey_clipboard"]:
            new_id, err = self.hotkeys.rebind(self.hk_clip_id, clip_spec)
            self.hk_clip_id = new_id
            if err:
                ok = False
                messages.append(err)
            else:
                CFG.set("hotkey_clipboard", clip_spec)
        if xray_spec and xray_spec != CFG["hotkey_xray"]:
            new_id, err = self.hotkeys.rebind(self.hk_xray_id, xray_spec)
            self.hk_xray_id = new_id
            if err:
                ok = False
                messages.append(err)
            else:
                CFG.set("hotkey_xray", xray_spec)
        self.refresh_tray()
        if messages:
            return ok, "; ".join(messages)
        if warnings:
            return ok, warnings[0]
        return ok, ("Shortcuts active: %s (tap to snip, hold to see "
                    "translated) and %s"
                    % (CFG["hotkey"].upper(),
                       CFG["hotkey_clipboard"].upper()))

    def set_run_at_startup(self, enabled):
        """Run at login: a LaunchAgent on macOS, an HKCU Run entry on Windows."""
        bundle = os.environ.get("SQUINT_BUNDLE", "")
        if getattr(sys, "frozen", False):
            command = [sys.executable]
        elif sys.platform == "darwin" and bundle.endswith(".app") \
                and os.path.isdir(bundle):
            # Started from the disk-image app. Its interpreter only works
            # with the environment its launcher sets up, so at login the
            # app is opened the way Finder opens it, launcher and all.
            command = ["/usr/bin/open", "-a", bundle]
        else:
            command = [sys.executable,
                       os.path.join(config.app_dir(), "run_app.py")]
        return platform_util.set_run_at_login(enabled, command)

    # -- lifecycle -----------------------------------------------------
    def show_window(self):
        if self.window is not None:
            self.root.after(0, self.window.show)

    def _confirm_visible(self):
        """Record whether the window actually made it onto the screen.

        'It did not open' and 'it opened behind everything' look identical
        from the outside, so the log has to distinguish them.
        """
        try:
            window = self.window
            log("window     : viewable=%s mapped=%s geometry=%s"
                % (bool(window.winfo_viewable()), bool(window.winfo_ismapped()),
                   window.winfo_geometry()))
            if not window.winfo_viewable():
                platform_util.raise_to_front(window)
                log("window     : forced to front")
        except Exception:
            log("window     : could not be inspected\n%s"
                % traceback.format_exc())

    def quit(self):
        # Separately, so that one failing does not skip the other. They
        # were in a single try: a hotkey manager that threw on the way out
        # left the tray icon behind, and a listener child process outlives
        # the app that started it — the next run then registers the same
        # shortcut against a process that is already holding it.
        self.release()
        try:
            self.root.after(0, self.root.destroy)
        except Exception:
            os._exit(0)

    def release(self):
        """Give back everything the OS is holding on this app's behalf.

        Called on the way out and registered with atexit, because "quit"
        is not the only way a program stops.
        """
        for shutdown in (getattr(self.hotkeys, "stop", None),
                         getattr(self.tray, "stop", None)):
            if shutdown is None:
                continue
            try:
                shutdown()
            except Exception:
                log(traceback.format_exc())
        # What holding the connections open was actually worth on this
        # machine and this network. One line at the end rather than one per
        # request: it is the comparison between the two averages that says
        # anything, and neither number can be guessed from a development
        # machine sitting next to a router.
        try:
            from . import http_pool
            spent = http_pool.POOL.summary()
            if spent:
                log("network    : %s" % spent)
            http_pool.POOL.clear()
        except Exception:
            pass

    def run(self):
        if not CFG.get("start_minimized"):
            self.show_window()
            self.root.after(250, self._confirm_visible)
        else:
            self.tray and self.tray.notify(
                "Running in the tray. Press %s to snip & translate."
                % CFG["hotkey"].upper())
        # Pay the first translation's costs now, while nobody is waiting —
        # see `warmup`. Here, in the one place that runs once per process,
        # and not in the window: the window is built many times over (a
        # theme change rebuilds it, and the test suite builds it dozens of
        # times), and a job that belongs to the process started from
        # something built that often ran concurrently with things it had
        # no business running beside.
        self.root.after(900, self._warm_up)
        self.root.mainloop()

    def _warm_up(self):
        try:
            from . import warmup
            warmup.start()
        except Exception:
            pass
        self._keep_startup_promise()
        self.root.after(15000, self._watch_google_billing)

    # How often the window looks for a Google billing notice to show. The
    # refusal is noted on a worker thread; the window is only ever touched
    # from this one.
    BILLING_WATCH_MS = 10000

    def _watch_google_billing(self):
        try:
            from . import google_billing
            google_billing.check_reminder()
            kind = google_billing.pending()
            if kind:
                from . import ui_billing
                log("google billing notice: %s" % kind)
                ui_billing.show(self.root, kind, palette=self.palette())
        except Exception:
            log(traceback.format_exc())
        try:
            self.root.after(self.BILLING_WATCH_MS, self._watch_google_billing)
        except Exception:
            pass

    def _keep_startup_promise(self):
        """Starting at login is on by default, so make it true.

        The setting said so on a fresh install while nothing was registered
        with the system: the installer registers it on Windows, but a copy
        set up any other way never did. Registering is idempotent and
        cheap, so whenever the setting is on and the system has no entry,
        the entry is made. Off is never forced on: that is the user's.
        """
        try:
            if not CFG.get("run_at_startup"):
                return
            if platform_util.run_at_login_is_set():
                return
            if platform_util.IS_WINDOWS or platform_util.IS_MAC:
                self.set_run_at_startup(True)
        except Exception:
            pass


def log_startup():
    """First lines of every run: which build, and what it will look like.

    Without this there is no way to tell a stale executable from a new one,
    which is the difference between a real bug and a rebuild that never ran.
    """
    from . import __version__
    log("")
    log("--- Squint %s starting ---" % __version__)
    log("exe        : %s" % (sys.executable if getattr(sys, "frozen", False)
                             else "(from source) " + sys.executable))
    log("frozen     : %s" % bool(getattr(sys, "frozen", False)))
    log("app dir    : %s" % config.app_dir())
    log("theme      : %s" % CFG.get("theme"))
    log("translucent: %s" % CFG.get("translucent"))
    log("safe mode  : %s" % ("--safe" in sys.argv))
    log("platform   : %s" % sys.platform)
    log("ocr engine : %s" % ocr.engine_name())
    log("resources  : %s" % config.resource_dir())


def show_native_error(title, message):
    """Report a failure without relying on the toolkit that just failed.

    If Tk is what broke, a Tk dialog cannot say so. macOS and Windows both
    have a way to put a box on screen without it.
    """
    try:
        if sys.platform == "darwin":
            import subprocess
            subprocess.run(
                ["osascript", "-e",
                 'display alert "%s" message "%s"'
                 % (title.replace('"', "'"), message.replace('"', "'")[:900])],
                capture_output=True, timeout=60)
            return True
        if sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(None, message[:900], title, 0x10)
            return True
    except Exception:
        pass
    return False


def _say_already_running():
    """Where to look, in the words of the platform it is said on."""
    if os.name == "nt":
        try:
            ctypes.windll.user32.MessageBoxW(
                None, "Squint is already running — look for the icon "
                      "in the system tray (bottom-right, under the ^ arrow).",
                "Squint", 0x40)
        except Exception:
            pass
        return
    try:
        import subprocess
        subprocess.run([
            "osascript", "-e",
            'display alert "Squint is already running" message '
            "\"Look for it in the menu bar, or press the shortcut. \n\n"
            'If you have two copies of Squint.app, delete one — they '
            'compete for the same keyboard shortcut."'], timeout=30)
    except Exception:
        pass


def main():
    # What was actually achieved, not what was asked for. The call can only
    # succeed once per process and fails silently if a packaged app's
    # manifest got there first — and if it did, every pixel the app
    # measures on a display set to a different scale is wrong, which looks
    # like a fault on two monitors of three rather than like a setting.
    awareness = snip.make_dpi_aware()
    log_startup()
    try:
        from . import tk_images
        tk_images.install()
    except Exception:
        pass
    if awareness:
        log("dpi        : %s" % awareness)
    # Before the first widget, and before anything asks Tk what fonts
    # exist: Tk reads the system's font list once and keeps the answer,
    # so a face registered after that is one Tk will say it does not
    # have. Costs nothing where it cannot work.
    try:
        from . import fonts as _fonts
        took = _fonts.register()
        log("fonts      : %s" % (", ".join(sorted(took)) if took
                                 else "system faces"))
    except Exception:
        pass
    if already_running():
        _say_already_running()
        return 0
    # An update replaces the code but not the app bundle that launches it,
    # so a fault in the launcher survives every release. Checked here, in
    # the background, and rebuilt only when it has fallen behind.
    try:
        from . import mac_bundle
        mac_bundle.start()
    except Exception:
        pass
    try:
        Controller().run()
    except Exception:
        detail = traceback.format_exc()
        log(detail)
        sys.stderr.write(detail)
        summary = detail.strip().splitlines()[-1] if detail.strip() else "?"
        # If the Mac app's Tk 8.6 swap is what stopped it, put Tk 9 back
        # so the next start works, and do not try the swap again.
        try:
            from . import mac_toolkit
            if mac_toolkit.undo_after_crash(detail):
                log("toolkit    : start failed on Tk 8.6; Tk 9 put back")
                summary += "\n\nSquint has undone its last change. Open it again."
        except Exception:
            pass
        if not show_native_error(
                "Squint could not start",
                "%s\n\nFull details: %s" % (summary, config.log_path())):
            try:
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror("Squint could not start", summary)
            except Exception:
                pass
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
