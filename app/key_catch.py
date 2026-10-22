"""Catch an API key the moment the user copies it.

Getting a Gemini key is: press a button here, a browser opens, press
"Create API key", press the copy icon, come back, click the box, paste. The
last three steps are the ones people lose. They copy the key, get
distracted by the browser tab, come back later and find an empty field with
no memory of whether they copied it or not — and the key page will not show
it again.

So Squint watches its own clipboard while that browser tab is open. When
something key-shaped appears on it, the field fills itself. Nothing is sent
anywhere and nothing is saved until the user presses Save & test; this only
does the typing.

Deliberately narrow. It runs only while a setup window is open and the user
has just pressed the button that opens the key page, it only ever matches
the two shapes Google issues, and it stops at the first match or after a
few minutes. A clipboard watcher that runs all the time is spyware, however
kindly meant.
"""
import re

# The two shapes Google issues. "AIza..." is the long-standing one;
# newer keys arrive as "AQ.<base64ish>", which is why the app sends keys in
# a header rather than a ?key= parameter — the query form rejects them.
PATTERNS = (
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"),
    re.compile(r"\bAQ\.[A-Za-z0-9_\-]{20,}\b"),
)

POLL_MS = 700
# Long enough to sign in, make a project and press copy; short enough that
# a forgotten window is not still reading the clipboard an hour later.
GIVE_UP_MS = 5 * 60 * 1000


def key_in(text):
    """The first thing shaped like a Google API key, or None."""
    if not text:
        return None
    for pattern in PATTERNS:
        found = pattern.search(str(text))
        if found:
            return found.group(0)
    return None


class Watcher:
    """Polls the clipboard until a key shows up, then calls back once.

    Tk has no clipboard-changed event, so this is a poll. 700ms is chosen
    to be invisible to a person and negligible to a machine; the whole
    thing lives for five minutes at most.
    """

    def __init__(self, widget, on_key, ignore=None):
        self.widget = widget
        self.on_key = on_key
        # Whatever was already on the clipboard is not a discovery. Without
        # this, opening the panel with a key copied an hour ago fills the
        # box from nowhere, which is indistinguishable from the app having
        # kept it.
        self.seen = {str(ignore or "")}
        self._job = None
        self._waited = 0
        self._alive = True

    def start(self):
        from . import clipboard
        try:
            self.seen.add(str(clipboard.get_text(self.widget) or ""))
        except Exception:
            pass
        self._tick()
        return self

    def stop(self):
        self._alive = False
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _tick(self):
        if not self._alive:
            return
        from . import clipboard
        try:
            current = str(clipboard.get_text(self.widget) or "")
        except Exception:
            current = ""
        if current and current not in self.seen:
            self.seen.add(current)
            found = key_in(current)
            if found:
                self.stop()
                try:
                    self.on_key(found)
                except Exception:
                    pass
                return
        self._waited += POLL_MS
        if self._waited >= GIVE_UP_MS:
            self.stop()
            return
        try:
            self._job = self.widget.after(POLL_MS, self._tick)
        except Exception:
            self.stop()
