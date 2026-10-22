"""The two macOS permissions Squint needs, and a short way through them.

**Accessibility** lets the clipboard shortcut press Cmd+C for you.
**Screen & System Audio Recording** lets a snip see the screen.

macOS lets no app switch either on for itself — only the person at the
Mac can, in System Settings. What an app can do is ask (which puts it in
the list, so there is a switch to flip), open the exact list, and notice
when the switch has been flipped. That is all this does.

Accessibility is read live, so it can be noticed the moment it is switched
on. Screen Recording is only read when the app starts — macOS itself
offers "Quit & Reopen" — so it is the second step, and the one restart
comes at the end.
"""
import ctypes
import ctypes.util
import subprocess
import sys

from . import selection

PANES = {
    "accessibility": "x-apple.systempreferences:com.apple.preference."
                     "security?Privacy_Accessibility",
    "screen": "x-apple.systempreferences:com.apple.preference."
              "security?Privacy_ScreenCapture",
}


def is_mac():
    return sys.platform == "darwin"


def _core_graphics():
    try:
        path = ctypes.util.find_library("CoreGraphics") or (
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        lib = ctypes.cdll.LoadLibrary(path)
        lib.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        lib.CGPreflightScreenCaptureAccess.argtypes = []
        lib.CGRequestScreenCaptureAccess.restype = ctypes.c_bool
        lib.CGRequestScreenCaptureAccess.argtypes = []
        return lib
    except Exception:
        return None


def accessibility_ok():
    if not is_mac():
        return True
    try:
        return bool(selection.permitted())
    except Exception:
        return False


def screen_ok():
    """Whether snips can see other apps' windows. As of the last start:
    macOS does not change the answer for a running app."""
    if not is_mac():
        return True
    lib = _core_graphics()
    if lib is None:
        return True          # too old to ask; it would have asked itself
    try:
        return bool(lib.CGPreflightScreenCaptureAccess())
    except Exception:
        return True


def open_pane(which):
    if not is_mac():
        return False
    try:
        subprocess.Popen(["open", PANES[which]])
        return True
    except Exception:
        return False


# The app's identity in the permission lists, when it runs as Squint.app.
BUNDLE_ID = "com.squint.app"
_SERVICES = {"accessibility": "Accessibility", "screen": "ScreenCapture"}


def _as_app():
    import os
    return bool(os.environ.get("SQUINT_BUNDLE"))


def forget_stale(which):
    """Remove Squint's entry from one list, so the next ask adds a fresh one.

    The app is signed ad hoc, and every build has a different signature. A
    switch flipped for an earlier build stays on in the list — it still
    reads "Squint", still shows blue — but macOS holds it to the old
    signature and refuses the new build. Flipping it again does nothing.
    Only a fresh entry fixes it, and `tccutil reset` for the app's own
    identifier makes one without asking for a password. Only ever called
    when the permission is not working, so it never takes away one that is.
    """
    if not is_mac() or not _as_app():
        return False
    try:
        subprocess.run(["tccutil", "reset", _SERVICES[which], BUNDLE_ID],
                       capture_output=True, timeout=10)
        return True
    except Exception:
        return False


def ask_accessibility():
    """Put Squint in the Accessibility list and open that list."""
    if not accessibility_ok():
        forget_stale("accessibility")
    try:
        selection.request_permission()
    except Exception:
        pass
    return open_pane("accessibility")


def ask_screen():
    """Put Squint in the Screen Recording list and open that list."""
    if not screen_ok():
        forget_stale("screen")
    lib = _core_graphics()
    if lib is not None:
        try:
            lib.CGRequestScreenCaptureAccess()
        except Exception:
            pass
    return open_pane("screen")


def all_ok():
    return accessibility_ok() and screen_ok()
