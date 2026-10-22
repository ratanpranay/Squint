"""Notice a mouse click anywhere on the screen, not just inside this app.

The translation card is meant to go away when you click somewhere else. It
did not, and the reason is that Tk's `bind_all` is not app-wide in the sense
the name suggests — it is *this application* wide. A click on Outlook, or a
browser, or the desktop is delivered to that program and Tk never hears
about it, so the card sat there over the page it was translating until it
was closed by hand.

Asking the operating system directly is the only way to know. On Windows
that is GetAsyncKeyState, which reports the physical button regardless of
who has focus; on macOS it is Quartz, which is already a dependency for
Vision. Both are read through a poll rather than a hook: a global mouse
hook is the sort of thing that gets an application flagged by security
software, and 8 polls a second is enough to feel immediate.

Nothing here reads *what* is clicked, or logs anything. It answers one
question — has the left button just gone down — and the caller compares the
pointer position it already has.
"""
import sys

INTERVAL = 120          # ms between checks; ~8 a second

_backend = None


def _windows_pressed():
    import ctypes
    # 0x01 is VK_LBUTTON. The high bit means "down right now".
    return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)


def _mac_pressed():
    from Quartz import CGEventSourceButtonState
    # 1 = kCGEventSourceStateCombinedSessionState, 0 = left button.
    return bool(CGEventSourceButtonState(1, 0))


def _pick_backend():
    global _backend
    if _backend is not None:
        return _backend
    try:
        if sys.platform == "win32":
            _windows_pressed()
            _backend = _windows_pressed
        elif sys.platform == "darwin":
            _mac_pressed()
            _backend = _mac_pressed
        else:
            _backend = False
    except Exception:
        _backend = False
    return _backend


def available():
    return bool(_pick_backend())


class Watcher:
    """Calls `on_click()` on the Tk thread when the button goes down.

    Only the transition matters: holding the button down is one click, and
    a button already held when the watcher starts is ignored, so the click
    that produced the card cannot also dismiss it.
    """

    def __init__(self, widget, on_click):
        self.widget = widget
        self.on_click = on_click
        self._job = None
        self._was_down = True        # assume down until proven otherwise
        self._stopped = False

    def start(self):
        if not available():
            return False
        self._tick()
        return True

    def stop(self):
        self._stopped = True
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _tick(self):
        if self._stopped:
            return
        try:
            if not self.widget.winfo_exists():
                return
        except Exception:
            return
        try:
            down = bool(_pick_backend()())
        except Exception:
            down = False
        if down and not self._was_down:
            self._was_down = True
            try:
                self.on_click()
            except Exception:
                pass
            if self._stopped:
                return
        elif not down:
            self._was_down = False
        try:
            self._job = self.widget.after(INTERVAL, self._tick)
        except Exception:
            self._job = None
