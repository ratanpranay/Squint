"""Platform differences in one place.

The app runs on Windows and macOS, and the differences are not cosmetic:
different hotkey APIs, different OCR engines, different ideas of a pixel.
Keeping the branching here means the rest of the code can stay unaware.
"""
import os
import subprocess
import sys

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = not IS_MAC and not IS_WINDOWS


def describe():
    """This machine, in one line, for a bug report.

    The name people use and the version, not the kernel build: "macOS
    14.5" is something a reporter recognises as their own computer and
    can confirm; "Darwin 23.5.0" is something they have to look up
    before they can tell you whether it is right.
    """
    import platform
    try:
        if IS_MAC:
            release = platform.mac_ver()[0] or platform.release()
            return "macOS %s (%s)" % (release, platform.machine())
        if IS_WINDOWS:
            return "Windows %s (%s)" % (platform.release(),
                                        platform.machine())
        return "%s %s (%s)" % (platform.system(), platform.release(),
                               platform.machine())
    except Exception:
        return sys.platform


def reveal(path):
    """Show a file where the user keeps files, rather than opening it.

    A log opened in whatever claims .log is a text editor is one thing;
    a log sitting selected in a folder is one the user can attach to a
    message, which is what they usually want it for.
    """
    try:
        import subprocess
        if IS_MAC:
            subprocess.Popen(["open", "-R", path])
            return True
        if IS_WINDOWS:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            return True
    except Exception:
        pass
    return open_path(path)


def open_path(path):
    """Reveal a file or folder in the system file manager."""
    try:
        if IS_WINDOWS:
            os.startfile(path)  # noqa: F821  (Windows only)
            return True
        if IS_MAC:
            subprocess.Popen(["open", path])
            return True
        subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


def open_accessibility_settings():
    """The Privacy & Security › Accessibility pane, in one step.

    "Open System Settings, then Privacy & Security, then scroll to
    Accessibility" is four instructions and a scroll, given to somebody who
    is already annoyed that a shortcut did not work. macOS has a URL for
    the pane; use it.
    """
    if not IS_MAC:
        return False
    try:
        subprocess.Popen([
            "open",
            "x-apple.systempreferences:com.apple.preference.security"
            "?Privacy_Accessibility"])
        return True
    except Exception:
        return False


# -- run at login ------------------------------------------------------
LAUNCH_AGENT_ID = "com.squint.agent"
# The agent this app used to install. Removed when autostart is
# touched, so a rename cannot leave something behind that keeps
# launching an app the user thinks they have replaced.
OLD_LAUNCH_AGENT_IDS = ("com.snaptranslate.agent",)


def _launch_agent_path():
    return os.path.expanduser(
        "~/Library/LaunchAgents/%s.plist" % LAUNCH_AGENT_ID)


def _clear_old_launch_agents():
    """Unload and delete agents installed under the app's previous name.

    Without this, renaming the app leaves a login item pointing at the old
    one: the user turns startup off in the new app and something still
    launches every morning, with no visible way to stop it.
    """
    base = os.path.expanduser("~/Library/LaunchAgents")
    for old_id in OLD_LAUNCH_AGENT_IDS:
        old = os.path.join(base, "%s.plist" % old_id)
        if not os.path.isfile(old):
            continue
        try:
            subprocess.run(["launchctl", "unload", old],
                           capture_output=True, timeout=20)
        except Exception:
            pass
        try:
            os.remove(old)
        except Exception:
            pass


def _mac_set_autostart(enabled, command):
    path = _launch_agent_path()
    _clear_old_launch_agents()
    if not enabled:
        try:
            if os.path.isfile(path):
                subprocess.run(["launchctl", "unload", path],
                               capture_output=True, timeout=20)
                os.remove(path)
            return True, ""
        except Exception as exc:
            return False, str(exc)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        args = "".join("        <string>%s</string>\n" % part
                       for part in command)
        plist = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n'
            '<dict>\n'
            '    <key>Label</key>\n'
            '    <string>%s</string>\n'
            '    <key>ProgramArguments</key>\n'
            '    <array>\n%s    </array>\n'
            '    <key>RunAtLoad</key>\n'
            '    <true/>\n'
            '</dict>\n'
            '</plist>\n' % (LAUNCH_AGENT_ID, args))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(plist)
        subprocess.run(["launchctl", "unload", path], capture_output=True,
                       timeout=20)
        subprocess.run(["launchctl", "load", path], capture_output=True,
                       timeout=20)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _windows_set_autostart(enabled, command):
    try:
        import winreg
    except ImportError:
        return False, "Windows only."
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                value = " ".join('"%s"' % part for part in command)
                winreg.SetValueEx(key, "Squint", 0, winreg.REG_SZ,
                                  value)
            else:
                try:
                    winreg.DeleteValue(key, "Squint")
                except FileNotFoundError:
                    pass
        return True, ""
    except Exception as exc:
        return False, str(exc)


def run_at_login_is_set():
    """Whether Windows is set to start Squint at login, whoever set it.

    The Settings switch remembered only its own answer. The installer
    turns this on as well — a copy that is already running when the
    shortcut is pressed is a copy with nothing left to load — and the
    switch then read "off" for something that was on. Asking the place
    Windows actually looks is the only answer that cannot disagree.
    """
    if IS_MAC:
        return os.path.isfile(_launch_agent_path())
    if not IS_WINDOWS:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_READ) as key:
            value, _kind = winreg.QueryValueEx(key, "Squint")
        return bool(str(value or "").strip())
    except Exception:
        return False


def set_run_at_login(enabled, command):
    if IS_MAC:
        return _mac_set_autostart(enabled, command)
    if IS_WINDOWS:
        return _windows_set_autostart(enabled, command)
    return False, "Not supported on this platform."


# -- Retina / HiDPI ----------------------------------------------------
def screen_scale(tk_widget, grabbed_width):
    """Physical pixels per logical point.

    macOS screenshots come back in *physical* pixels — 2x on a Retina
    display — while Tk positions windows in logical points. Getting this
    wrong puts the overlay at half or double the intended position, which is
    the classic Retina bug.
    """
    try:
        logical = tk_widget.winfo_screenwidth()
        if logical > 0 and grabbed_width > 0:
            ratio = grabbed_width / float(logical)
            # Only ever 1x, 2x or 3x in practice; anything else is noise.
            for candidate in (1.0, 2.0, 3.0):
                if abs(ratio - candidate) < 0.12:
                    return candidate
            return max(1.0, round(ratio, 2))
    except Exception:
        pass
    return 1.0


# -- Which screen a window belongs on ----------------------------------
#
# Tk's idea of "the screen" is one display — the main one — and every
# other display is off the end of it. That is fine on a laptop and wrong
# on a desk, and wrong in a way that looks like the app ignoring where the
# work is happening: a translation of something snipped on the right-hand
# monitor was pulled back onto the main screen, because the only width it
# had to clamp against was the main screen's.
#
# The screen grabber already knows where every display is, and is asked
# here for nothing but that. The answer is cached for a moment because it
# is asked once per window and does not change between two of them.
_DISPLAY_CACHE = {"at": 0.0, "value": None}
_DISPLAY_TTL = 2.0


def displays(refresh=False):
    """Every display as (left, top, width, height), in device pixels.

    Empty when there is no way to ask, which every caller has to treat as
    "fall back to whatever Tk says" rather than as an error.
    """
    import time
    now = time.time()
    if not refresh and _DISPLAY_CACHE["value"] is not None \
            and now - _DISPLAY_CACHE["at"] < _DISPLAY_TTL:
        return _DISPLAY_CACHE["value"]
    found = []
    try:
        import mss
        with mss.mss() as sct:
            # [0] is the union of them all, which is the thing this exists
            # to stop being treated as a screen.
            for mon in list(sct.monitors[1:]) or list(sct.monitors[:1]):
                found.append((int(mon["left"]), int(mon["top"]),
                              int(mon["width"]), int(mon["height"])))
    except Exception:
        found = []
    _DISPLAY_CACHE["at"], _DISPLAY_CACHE["value"] = now, found
    return found


def _overlap(rect, display):
    x, y, w, h = rect
    left, top, width, height = display
    across = min(x + w, left + width) - max(x, left)
    down = min(y + h, top + height) - max(y, top)
    return max(0, across) * max(0, down)


def display_for(x, y, width, height, scale=1.0, known=None):
    """The display a window of this size at this position mostly sits on.

    Chosen by how much of the window lands on each, not by where its
    corner is: a window whose top-left is a few pixels off the edge of a
    display belongs to that display, not to its neighbour.

    `scale` converts device pixels to whatever the caller is measuring in,
    so a Retina Mac can ask this question in points.
    """
    found = known if known is not None else displays()
    if not found:
        return None
    scale = float(scale) or 1.0
    rect = (float(x), float(y), max(1.0, float(width)), max(1.0, float(height)))
    best, score = None, -1.0
    for display in found:
        scaled = tuple(v / scale for v in display)
        seen = _overlap(rect, scaled)
        if seen > score:
            best, score = scaled, seen
    return best


def clamp_to_display(x, y, width, height, scale=1.0, fallback=None,
                     known=None):
    """Pull a window back onto the display it belongs to.

    `fallback` is `(screen_width, screen_height)` — Tk's answer — used
    when the displays cannot be asked for. That was the only answer
    before, and it is the right one on a single screen.

    A window bigger than its display is left at that display's edge rather
    than being pushed off the far side, which is what clamping the wrong
    way round does.
    """
    x, y = int(x), int(y)
    width, height = max(1, int(width)), max(1, int(height))
    display = display_for(x, y, width, height, scale, known)
    if display is None:
        if not fallback:
            return x, y
        screen_w, screen_h = fallback
        left, top = 0, 0
        span_w, span_h = int(screen_w), int(screen_h)
    else:
        left, top, span_w, span_h = (int(round(v)) for v in display)
    if width >= span_w:
        x = left
    else:
        x = max(left, min(x, left + span_w - width))
    if height >= span_h:
        y = top
    else:
        y = max(top, min(y, top + span_h - height))
    return x, y


def room_on_display(x, y, scale=1.0, fallback=None, known=None):
    """How much space there is on the display at this point.

    The overlay grows to a share of the screen before it starts
    scrolling, and on a desk that share has to be of the screen the work
    is on. Measuring it against the main display makes the overlay too
    small on a large second monitor and too big on a small one — and too
    big means it hangs off the edge, which is the failure it was written
    to avoid.
    """
    display = display_for(x, y, 1, 1, scale, known)
    if display is None:
        return tuple(fallback) if fallback else None
    return int(round(display[2])), int(round(display[3]))


# -- How Windows reports pixels ----------------------------------------
#
# Three settings, and which one the process ends up in decides whether
# every measurement the app makes is in real pixels or in a lie:
#
#   unaware      Windows scales the whole process. A 4K display at 150%
#                is reported as 2560 wide, and what is grabbed from it is
#                a stretched copy of a smaller picture. Text read from
#                that is soft, and everything placed on it is placed in
#                coordinates that are not the screen's.
#   system       Real pixels for displays at the *system* scale, and the
#                same lie for every display set to a different one. This
#                is the setting that makes a desk of mixed monitors go
#                wrong on two screens out of three while looking perfect
#                on the third.
#   per-monitor  Real pixels everywhere. What this app needs.
#
# It can only be set once per process and only before the first window,
# and the call fails silently if something set it first — a packaged app's
# manifest can. `SetProcessDpiAwareness` returns a result code rather than
# raising, so the old spelling could not tell success from failure and
# assumed success. Now it is checked, and what was actually achieved is
# reported so it can be written into the log.
DPI_UNAWARE, DPI_SYSTEM, DPI_PER_MONITOR = 0, 1, 2
_DPI_NAMES = {DPI_UNAWARE: "unaware", DPI_SYSTEM: "system",
              DPI_PER_MONITOR: "per-monitor"}

# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2, as a handle-shaped constant.
_PER_MONITOR_V2 = -4


def _windll():
    """The Windows API, or None. A seam so this can be tested off Windows."""
    if not IS_WINDOWS:
        return None
    try:
        import ctypes
        return ctypes.windll
    except Exception:
        return None


def dpi_awareness():
    """What this process is actually set to, as a name, or "" if unknown."""
    api = _windll()
    if api is None:
        return ""
    try:
        import ctypes
        value = ctypes.c_int(-1)
        if api.shcore.GetProcessDpiAwareness(None, ctypes.byref(value)) == 0:
            return _DPI_NAMES.get(value.value, "unknown (%d)" % value.value)
    except Exception:
        pass
    try:
        return "system" if api.user32.IsProcessDPIAware() else "unaware"
    except Exception:
        return ""


def _mac_high_resolution():
    """Ask macOS to draw this process at the screen's real resolution.

    A Mac with a Retina display has two device pixels to the point. A
    process that has not said it can cope is drawn at one pixel to the
    point and the result is scaled up by the window server, which is
    exactly what it sounds like: every line in the window twice as wide
    as it should be, every curve stepped, and a photograph at half the
    resolution it was prepared at. It is not a fault in any one thing
    that is drawn, which is why chasing it one widget at a time — the
    icons, the pills, the photograph — got nowhere.

    A bundle says so in its Info.plist and Squint.app does. But the app
    is run from source as often as from the bundle: `Squint.command`, a
    Terminal launch, a debug run, and the bundle's own launcher when it
    falls back to the environment's interpreter. In all of those the
    process belongs to whatever Info.plist the Python framework carries,
    and that is not something this project gets to choose.

    So it is asked for at runtime instead. The main bundle's info
    dictionary is mutable before the first window exists, and that is
    where this is called from — the first line of `main`, ahead of Tk,
    ahead of the tray, ahead of anything that could put a window up.

    Returns what happened, which goes into the launch log: on a machine
    where this is somehow not the answer, the log says so rather than
    leaving somebody guessing again.
    """
    try:
        from Foundation import NSBundle
    except Exception as exc:
        return "no pyobjc (%s)" % str(exc)[:60]
    try:
        bundle = NSBundle.mainBundle()
        if bundle is None:
            return "no main bundle"
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info is None:
            return "no bundle info"
        if bool(info.get("NSHighResolutionCapable", False)):
            return "already high resolution"
        info["NSHighResolutionCapable"] = True
        return "high resolution asked for"
    except Exception as exc:
        return "could not ask (%s)" % str(exc)[:60]


def make_dpi_aware():
    """Ask the system for real pixels. Returns what was actually achieved.

    Best first. Per-monitor v2 is the only one that keeps reporting real
    pixels as a window moves between displays set to different scales,
    which is the case this exists for; the older per-monitor setting is
    next; the system-wide one is a poor third and is still far better than
    nothing.

    macOS needs something quite different and used to be told it needed
    nothing — see `_mac_high_resolution`. Linux genuinely needs none of
    it.
    """
    if IS_MAC:
        return _mac_high_resolution()
    if not IS_WINDOWS:
        return "not Windows"
    api = _windll()
    if api is None:
        return "unavailable"
    try:
        import ctypes
        fn = api.user32.SetProcessDpiAwarenessContext
        fn.restype = ctypes.c_int
        fn.argtypes = [ctypes.c_void_p]
        if fn(ctypes.c_void_p(_PER_MONITOR_V2)):
            return "per-monitor v2"
    except Exception:
        pass
    try:
        # A result code, not an exception. Zero is success; anything else
        # means somebody set this first and the setting stands.
        if api.shcore.SetProcessDpiAwareness(DPI_PER_MONITOR) == 0:
            return "per-monitor"
    except Exception:
        pass
    try:
        if api.user32.SetProcessDPIAware():
            return "system"
    except Exception:
        pass
    already = dpi_awareness()
    return ("already set to %s" % already) if already else "could not be set"


def monitor_scaling(x, y):
    """The scale factor Windows is drawing the display at this point with.

    100 for a display at 100%, 150 for one at 150%. Zero where it cannot
    be asked. A desk where these differ is the case that goes wrong
    quietly: the app is correct on the display whose scale matches the
    process's, and wrong on the others, so it looks like an intermittent
    fault rather than a settings one.
    """
    api = _windll()
    if api is None:
        return 0
    try:
        import ctypes

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        monitor = api.user32.MonitorFromPoint(
            POINT(int(x), int(y)), 2)          # MONITOR_DEFAULTTONEAREST
        across = ctypes.c_uint()
        down = ctypes.c_uint()
        if api.shcore.GetDpiForMonitor(
                monitor, 0,                    # MDT_EFFECTIVE_DPI
                ctypes.byref(across), ctypes.byref(down)) == 0:
            return int(round(across.value * 100 / 96.0))
    except Exception:
        pass
    return 0


def become_foreground_app():
    """Make this process a real, frontmost macOS application.

    A Python process started from a venv is a *background* process as far as
    macOS is concerned. Tk will happily create windows, but they are never
    brought forward and the app gets no Dock presence — so the app looks like
    it did not start at all, while in fact it is running perfectly.

    Setting the activation policy to Regular is what promotes it. This must
    happen on the main thread, before the UI is shown.

    Returns a short status string for the log; never raises.
    """
    if not IS_MAC:
        return "n/a"
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyRegular
    except Exception as exc:
        return "AppKit unavailable (%s)" % exc
    try:
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)
        return "foreground app"
    except Exception as exc:
        return "failed: %s" % exc


def set_dock_icon(png_path):
    """Show Squint's icon in the Dock, whatever executable is running.
    Returns a short status for the log; never raises."""
    if not IS_MAC:
        return "n/a"
    try:
        from AppKit import NSApplication, NSImage
        image = NSImage.alloc().initWithContentsOfFile_(png_path)
        if image is None:
            return "could not read the icon"
        NSApplication.sharedApplication().setApplicationIconImage_(image)
        return "set"
    except Exception as exc:
        return "failed: %s" % exc


def frontmost_app():
    """Which application the OS considers active, for the log.

    "The app opens on top and then the translation appears" has two
    completely different causes and the same appearance. Either a window
    of Squint's own — a settings window left open — was raised because
    something activated the process, or nothing was raised at all and what
    came up was the small pill that says it is working.

    From a log that only says a card was drawn, those cannot be told apart,
    and guessing between them is how an evening goes. This answers it in
    one word. Empty everywhere but macOS, where the question does not
    arise, and empty rather than raising if AppKit is not there.
    """
    if not IS_MAC:
        return ""
    try:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return str(app.localizedName() or "") if app is not None else ""
    except Exception:
        return ""


# Windows the shell owns: the taskbar and the tray's overflow. A click on
# the tray icon brings these to the front, so they are never "the window
# the user was working in".
_SHELL_CLASSES = ("Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                  "NotifyIconOverflowWindow",
                  "TopLevelWindowForOverflowXamlIsland",
                  "Windows.UI.Core.CoreWindow", "Progman", "WorkerW")


def front_handle():
    """Something that can bring back the app in front now: its process id
    on macOS, its window on Windows. None when that is Squint itself, the
    taskbar, or cannot be told."""
    try:
        if IS_MAC:
            from AppKit import NSWorkspace
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app is None:
                return None
            pid = int(app.processIdentifier())
            return None if pid == os.getpid() else pid
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if int(pid.value) == os.getpid():
                return None
            name = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(hwnd, name, 128)
            if name.value in _SHELL_CLASSES:
                return None
            return int(hwnd)
    except Exception:
        return None
    return None


def bring_back(handle):
    """Put the app from `front_handle` in front again. True if asked."""
    if not handle:
        return False
    try:
        if IS_MAC:
            from AppKit import NSRunningApplication
            app = NSRunningApplication \
                .runningApplicationWithProcessIdentifier_(int(handle))
            if app is None:
                return False
            # NSApplicationActivateIgnoringOtherApps
            return bool(app.activateWithOptions_(1 << 1))
        if sys.platform == "win32":
            import ctypes
            user32 = ctypes.windll.user32
            if not user32.IsWindow(handle):
                return False
            return bool(user32.SetForegroundWindow(handle))
    except Exception:
        return False
    return False


# macOS virtual key codes, for the few keys that have to be read without
# going through the window that is supposed to have focus.
# The modifiers are here so that "is the shortcut even reaching this
# machine" can be answered without an event tap and without a permission.
# A whole evening went into a dead shortcut that no tool could tell apart
# from a key that was never pressed.
_MAC_KEYCODES = {"escape": 53, "return": 36,
                 "cmd": 55, "shift": 56, "capslock": 57, "alt": 58,
                 "ctrl": 59, "rshift": 60, "ralt": 61, "rctrl": 62,
                 "fn": 63, "rcmd": 54}


def key_is_down(name):
    """Is that key physically held right now? macOS only; False elsewhere.

    The snip overlay is a borderless window, and a borderless window on
    macOS takes mouse clicks perfectly well while never becoming the *key*
    window — and a key press is only delivered to the key window. That is
    the whole of why dragging a selection worked and Escape did nothing:
    the overlay was never listening, and no amount of lift(), focus_force()
    or focus_set() from Tk changes what AppKit considers key.

    Asking the window server what is held down sidesteps focus entirely.
    CGEventSourceKeyState is a state query rather than an event tap, so it
    needs no Accessibility permission — unlike the synthetic Cmd+C in
    selection.py, which does.
    """
    if not IS_MAC:
        return False
    code = _MAC_KEYCODES.get(name)
    if code is None:
        return False
    asker = _key_state()
    if asker is None:
        return False
    try:
        return bool(asker(code))
    except Exception:
        return False


_key_asker = "not tried"


def _key_state():
    """The window-server call, looked up once.

    This is asked eight times a second while a translation card is open,
    and `from Quartz import ...` on every one of those is work that has no
    business happening in a timer. Held here after the first success — and
    after the first failure too, so a machine without pyobjc does not pay
    for an import that will never work.
    """
    global _key_asker
    if _key_asker != "not tried":
        return _key_asker
    try:
        from Quartz import (CGEventSourceKeyState,
                            kCGEventSourceStateHIDSystemState)
        state = kCGEventSourceStateHIDSystemState
        _key_asker = lambda code: CGEventSourceKeyState(state, code)
    except Exception:
        _key_asker = None
    return _key_asker


def raise_to_front(window):
    """Bring a window forward on macOS, where lift() alone often is not
    enough for a process that was not launched as a bundled app."""
    try:
        window.lift()
        window.attributes("-topmost", True)
        window.after(300, lambda: _drop_topmost(window))
    except Exception:
        pass
    if IS_MAC:
        try:
            from AppKit import NSApplication
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except Exception:
            pass


def _drop_topmost(window):
    try:
        window.attributes("-topmost", False)
    except Exception:
        pass


def tray_supported():
    """Whether a system-tray icon is safe to start.

    Not on macOS. pystray's backend there drives AppKit, which — like the
    Text Input Services API that already crashed the hotkey listener — must
    be used from the main thread. Tk owns that thread, so starting the tray
    aborts the process rather than failing politely. The main window is the
    entry point on macOS instead.
    """
    return not IS_MAC


def default_xray_hotkey():
    """Hold to see the screen translated. The same on both systems: on a
    Mac, Alt is the Option key."""
    return "ctrl+alt+x"


def default_hotkeys():
    """Defaults chosen to avoid shortcuts other apps already own.

    Not cmd+shift+T or cmd+shift+C on macOS: every browser uses the first for
    "reopen closed tab" and the second for developer tools. ctrl+cmd is used
    by the system for only a handful of keys (F, D, Space), so T and C are
    free.
    """
    if IS_MAC:
        return "ctrl+cmd+x", "ctrl+cmd+c"
    return "ctrl+alt+x", "ctrl+alt+c"
