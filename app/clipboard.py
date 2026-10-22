"""Read the clipboard, including text that is not Latin.

Tk's `clipboard_get()` with no arguments asks the system for the `STRING`
target. On Windows that maps to CF_TEXT — the *ANSI* clipboard format,
which predates Unicode and holds text in the machine's legacy code page.
Copy Chinese out of a browser on an English-locale PC and CF_TEXT either
does not exist or contains question marks, so the call raises and the app
reports "Clipboard has no text" about a clipboard that plainly has text in
it.

Windows has held the real text in CF_UNICODETEXT the whole time. So on
Windows the clipboard is read directly, and Tk is the fallback rather than
the other way round. Everywhere else Tk is fine, as long as UTF8_STRING is
asked for before STRING.

This is the same class of bug as the OCR one: the machine was asked the
wrong question and answered it correctly.
"""
import sys
import time

CF_UNICODETEXT = 13
# Another program can hold the clipboard open for a few milliseconds after
# a copy. Failing on the first attempt would make this feel intermittent,
# which is worse than failing every time.
ATTEMPTS = 5
RETRY_DELAY = 0.02


def sequence():
    """Windows' clipboard change counter, or None where there is not one.

    The only reliable way to know whether a copy actually put something on
    the clipboard. Comparing the text before and after cannot tell a copy
    that did nothing from a copy of the same thing that was already there —
    and worse, if the "before" read fails and comes back empty, whatever
    was already on the clipboard then looks like a fresh selection. That is
    how a paragraph of German produced the release notes the user had
    copied ten minutes earlier, labelled "selection".

    GetClipboardSequenceNumber increments on every change by anyone. It
    needs no handle, opens nothing, and cannot be fooled by the contents.
    """
    if sys.platform == "darwin":
        # The Mac has one too: the pasteboard's change count. Without it a
        # copy that did nothing could not be told from one that did, and
        # the paragraph copied earlier was translated as if it were the
        # one just selected.
        try:
            from AppKit import NSPasteboard
            return int(NSPasteboard.generalPasteboard().changeCount())
        except Exception:
            return None
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetClipboardSequenceNumber.restype = ctypes.c_uint
        return int(user32.GetClipboardSequenceNumber())
    except Exception:
        return None


def _windows_text():
    """Read CF_UNICODETEXT with ctypes. Returns None when unavailable."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return None

    opened = False
    for _ in range(ATTEMPTS):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(RETRY_DELAY)
    if not opened:
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            # The handle belongs to the clipboard, so the text is copied
            # out rather than referenced — it stops being valid the moment
            # the clipboard is closed.
            return ctypes.c_wchar_p(pointer).value
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _tk_text(widget):
    """Ask Tk, most specific target first.

    UTF8_STRING before STRING matters on Linux too: STRING is Latin-1 by
    the ICCCM, so asking for it first gets mojibake for anything else.
    """
    for kind in ("UTF8_STRING", None, "STRING"):
        try:
            if kind is None:
                value = widget.clipboard_get()
            else:
                value = widget.clipboard_get(type=kind)
        except Exception:
            continue
        if value:
            return value
    return None


def get_text(widget=None):
    """Whatever text is on the clipboard, or "" — never raises."""
    if sys.platform == "win32":
        try:
            native = _windows_text()
        except Exception:
            native = None
        if native:
            return native
    if widget is not None:
        try:
            value = _tk_text(widget)
        except Exception:
            value = None
        if value:
            return value
    if sys.platform != "win32":
        return ""
    # One last try through Tk on Windows, for the case where the text is
    # only in CF_TEXT — an old application that never learned Unicode.
    try:
        return _tk_text(widget) or "" if widget is not None else ""
    except Exception:
        return ""


def set_text(widget, text):
    """Put text on the clipboard through Tk, which is reliable in this
    direction: Tk offers UTF8_STRING and Windows converts down as needed."""
    try:
        widget.clipboard_clear()
        widget.clipboard_append(text)
        widget.update()
        return True
    except Exception:
        return False
