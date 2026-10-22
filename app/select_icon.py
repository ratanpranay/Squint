"""A small Squint icon beside text you have just selected, in any app.
Click it and the selection is translated, as Ctrl+Alt+C would.

Three parts:

Noticing a selection. The mouse button is read about 25 times a second
(the same question app/click_watch.py asks: is the left button down), and
a selection is what people make with it: a drag, or a double or triple
click. Nothing is hooked into other programs and nothing they show is
read here.

Making sure it was text. A drag also moves windows, files and drawings.
On a Mac the system is asked for the selected text of the app in front
(Accessibility, the permission Squint already has for copying); no text,
no icon. That text is what gets translated, so the clipboard is not
touched. On Windows the pointer is asked what it looked like when the
drag began: the text cursor (the I-beam) is how every Windows program
says "this is text"; a window or a file is dragged with the arrow.

The icon. Squint's logo, by the end of the selection. It does not take
the keyboard from the app you are in - on a Mac it is a panel that never
activates Squint, on Windows a window that cannot be activated - and it
goes after a few seconds, on a click anywhere else, or when you click it.
"""
import os
import sys
import threading
import time

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

POLL = 40                 # ms between looks at the mouse button
DRAG = 8                  # points the pointer has to move to be a drag
DOUBLE = 0.5              # seconds between clicks of a double click
NEAR = 6                  # points apart the clicks of a double click may be
SHOW_FOR = 4.0            # seconds the icon stays when left alone
SIZE = 28                 # points
OFFSET = (10, 12)         # from the pointer, down and right
LONGEST = 5000            # characters; more is a document, not a selection


def _logo_path():
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (os.path.join(here, "..", "assets", "brand"),
                 os.path.join(here, "..", "assets")):
        for name in ("squint-icon-blue.png", "icon.png"):
            path = os.path.normpath(os.path.join(base, name))
            if os.path.isfile(path):
                return path
    return None


# -- Is it text? ---------------------------------------------------------

_IBEAM = 32513            # IDC_IBEAM


def windows_cursor_is_text():
    """Whether the pointer is the text cursor right now (Windows)."""
    if not IS_WINDOWS:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class CURSORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD),
                        ("flags", wintypes.DWORD),
                        ("hCursor", wintypes.HANDLE),
                        ("ptScreenPos", wintypes.POINT)]
        user32 = ctypes.windll.user32
        info = CURSORINFO()
        info.cbSize = ctypes.sizeof(CURSORINFO)
        if not user32.GetCursorInfo(ctypes.byref(info)):
            return False
        user32.LoadCursorW.restype = wintypes.HANDLE
        ibeam = user32.LoadCursorW(None, ctypes.c_void_p(_IBEAM))
        return bool(info.hCursor) and info.hCursor == ibeam
    except Exception:
        return False


_ax_lib = {}
_manual_set = set()


def _ax():
    """ApplicationServices and CoreFoundation through ctypes: pyobjc's
    ApplicationServices package is not installed (see selection.permitted
    for why ctypes)."""
    if _ax_lib:
        return _ax_lib
    import ctypes
    import ctypes.util
    from ctypes import POINTER, c_bool, c_char_p, c_float, c_int, c_int32, \
        c_long, c_uint32, c_ulong, c_void_p
    ax = ctypes.cdll.LoadLibrary(
        ctypes.util.find_library("ApplicationServices") or
        "/System/Library/Frameworks/ApplicationServices.framework/"
        "ApplicationServices")
    cf = ctypes.cdll.LoadLibrary(
        ctypes.util.find_library("CoreFoundation") or
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    ax.AXUIElementCreateSystemWide.restype = c_void_p
    ax.AXUIElementCreateSystemWide.argtypes = []
    ax.AXUIElementCreateApplication.restype = c_void_p
    ax.AXUIElementCreateApplication.argtypes = [c_int]
    ax.AXUIElementCopyAttributeValue.restype = c_int32
    ax.AXUIElementCopyAttributeValue.argtypes = [c_void_p, c_void_p,
                                                 POINTER(c_void_p)]
    ax.AXUIElementSetAttributeValue.restype = c_int32
    ax.AXUIElementSetAttributeValue.argtypes = [c_void_p, c_void_p,
                                                c_void_p]
    ax.AXUIElementSetMessagingTimeout.restype = c_int32
    ax.AXUIElementSetMessagingTimeout.argtypes = [c_void_p, c_float]
    cf.CFStringCreateWithCString.restype = c_void_p
    cf.CFStringCreateWithCString.argtypes = [c_void_p, c_char_p, c_uint32]
    cf.CFRelease.restype = None
    cf.CFRelease.argtypes = [c_void_p]
    cf.CFGetTypeID.restype = c_ulong
    cf.CFGetTypeID.argtypes = [c_void_p]
    cf.CFStringGetTypeID.restype = c_ulong
    cf.CFStringGetTypeID.argtypes = []
    cf.CFStringGetLength.restype = c_long
    cf.CFStringGetLength.argtypes = [c_void_p]
    cf.CFStringGetMaximumSizeForEncoding.restype = c_long
    cf.CFStringGetMaximumSizeForEncoding.argtypes = [c_long, c_uint32]
    cf.CFStringGetCString.restype = c_bool
    cf.CFStringGetCString.argtypes = [c_void_p, c_char_p, c_long, c_uint32]
    _ax_lib.update(ax=ax, cf=cf, true=c_void_p.in_dll(cf, "kCFBooleanTrue"),
                   ctypes=ctypes)
    return _ax_lib


_UTF8 = 0x08000100


def _cfstr(name):
    lib = _ax()
    return lib["cf"].CFStringCreateWithCString(None, name.encode("utf-8"),
                                               _UTF8)


def _copy(element, name):
    lib = _ax()
    ctypes = lib["ctypes"]
    key = _cfstr(name)
    out = ctypes.c_void_p()
    try:
        err = lib["ax"].AXUIElementCopyAttributeValue(element, key,
                                                      ctypes.byref(out))
    finally:
        lib["cf"].CFRelease(key)
    return out.value if err == 0 and out.value else None


def _string(value):
    lib = _ax()
    cf, ctypes = lib["cf"], lib["ctypes"]
    if not value or cf.CFGetTypeID(value) != cf.CFStringGetTypeID():
        return None
    size = cf.CFStringGetMaximumSizeForEncoding(cf.CFStringGetLength(value),
                                                _UTF8) + 1
    buf = ctypes.create_string_buffer(max(1, size))
    if not cf.CFStringGetCString(value, buf, size, _UTF8):
        return None
    return buf.value.decode("utf-8", "replace")


# What a press on text lands on, as the system describes it. A drag that
# began on one of these selected text even when the app will not say what
# the text is.
_TEXT_ROLES = ("AXStaticText", "AXWebArea", "AXHeading", "AXLink")
# Text that is also a control - a field, a cell, a file name in a list: a
# drag there may be moving it rather than selecting, so the icon waits for
# the app to say something is selected.
_FIELD_ROLES = ("AXTextArea", "AXTextField", "AXCell")
# When to ask again for the selected text after the button comes up: a
# browser settles its selection a moment after the release, and the first
# question after it switches on its description of the page is answered
# with nothing.
RETRIES = (0.0, 0.15, 0.35)


def _selected(system):
    lib = _ax()
    cf = lib["cf"]
    focused = _copy(system, "AXFocusedUIElement")
    if not focused:
        return None
    try:
        value = _copy(focused, "AXSelectedText")
        try:
            return _string(value)
        finally:
            if value:
                cf.CFRelease(value)
    finally:
        cf.CFRelease(focused)


def _role_at(system, at):
    """The role of what is at screen point `at` (top left of the main
    screen, points), or None."""
    if not at:
        return None
    lib = _ax()
    ax, cf, ctypes = lib["ax"], lib["cf"], lib["ctypes"]
    fn = ax.AXUIElementCopyElementAtPosition
    fn.restype = ctypes.c_int32
    fn.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float,
                   ctypes.POINTER(ctypes.c_void_p)]
    element = ctypes.c_void_p()
    if fn(system, float(at[0]), float(at[1]), ctypes.byref(element)) != 0 \
            or not element.value:
        return None
    try:
        value = _copy(element.value, "AXRole")
        try:
            return _string(value)
        finally:
            if value:
                cf.CFRelease(value)
    finally:
        cf.CFRelease(element.value)


def _switch_on(pid):
    """Ask Chrome, Edge, Brave and apps built like them to describe their
    pages to the system - they do only when told someone is asking, as
    screen readers do. Once per app."""
    if not pid or pid in _manual_set:
        return False
    _manual_set.add(pid)
    lib = _ax()
    ax, cf = lib["ax"], lib["cf"]
    app = ax.AXUIElementCreateApplication(int(pid))
    if not app:
        return False
    try:
        key = _cfstr("AXManualAccessibility")
        ax.AXUIElementSetAttributeValue(app, key, lib["true"])
        cf.CFRelease(key)
    finally:
        cf.CFRelease(app)
    return True


def mac_selected_text(pid=None, at=None):
    """Whether a selection was made, and its text when the app says (macOS).

    One rule: the press began on text - the system says what is under the
    pointer - so the drag or double click selected text, and the icon is
    shown (True). The text itself is asked for when the icon is clicked
    (mac_selection_now), by when every app has settled its selection;
    asked the instant the button came up, a browser answered "nothing" and
    the icon did not appear. Only if the press was not on anything the
    system calls text is the selection asked for here, for apps that do
    not describe what is under the pointer.

    Chrome, Brave, Edge and apps built like them describe their pages to
    the system only when told someone is asking; they are told once
    (AXManualAccessibility), the way screen readers do.

    Returns True, the selected text, or "" for no selection."""
    if not IS_MAC:
        return ""
    try:
        lib = _ax()
        ax, cf = lib["ax"], lib["cf"]
        system = ax.AXUIElementCreateSystemWide()
        if not system:
            return ""
        ax.AXUIElementSetMessagingTimeout(system, 0.3)
        try:
            if _switch_on(pid):
                time.sleep(0.15)       # it builds its description first
            role = _role_at(system, at)
            if role in _TEXT_ROLES:
                return True
            for wait in RETRIES:
                if wait:
                    time.sleep(wait)
                text = _selected(system)
                if text and text.strip():
                    return text
        finally:
            cf.CFRelease(system)
    except Exception:
        return ""
    return ""


def mac_selection_now(pid=None):
    """The selected text in the app in front, asked now (macOS), or ""."""
    if not IS_MAC:
        return ""
    try:
        lib = _ax()
        ax, cf = lib["ax"], lib["cf"]
        system = ax.AXUIElementCreateSystemWide()
        if not system:
            return ""
        ax.AXUIElementSetMessagingTimeout(system, 0.3)
        try:
            return (_selected(system) or "").strip()
        finally:
            cf.CFRelease(system)
    except Exception:
        return ""


# -- The icon --------------------------------------------------------------

class TkIcon:
    """The icon as a small Tk window (Windows, and anywhere without
    AppKit). On Windows it is made a window that cannot be activated, so
    a click on it leaves the keyboard - and the selection - with the app
    the text is in."""

    def __init__(self, root, on_click):
        import tkinter as tk
        self.root = root
        self.on_click = on_click
        self.scale = 1.0
        if IS_WINDOWS:
            try:
                self.scale = max(1.0, float(root.winfo_fpixels("1i")) / 96.0)
            except Exception:
                pass
        self.size = int(round(SIZE * self.scale))
        win = tk.Toplevel(root)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        self.win = win
        self.photo = self._photo(win)
        canvas = tk.Canvas(win, width=self.size, height=self.size,
                           highlightthickness=0, bd=0, bg="#2f5bff")
        canvas.pack()
        if self.photo is not None:
            canvas.create_image(0, 0, anchor="nw", image=self.photo)
        canvas.configure(cursor="hand2")
        canvas.bind("<ButtonRelease-1>", lambda _e: self.on_click())
        self.canvas = canvas
        self._styled = False

    def _photo(self, master):
        """The logo at the icon's size in real pixels, its corners filled
        with its own blue: Windows 11 rounds the window itself, smoothly,
        where a see-through corner would be a jagged one."""
        try:
            from PIL import Image, ImageTk
            path = _logo_path()
            if not path:
                return None
            logo = Image.open(path).convert("RGBA")
            blue = logo.getpixel((logo.width // 2, logo.height // 8))
            flat = Image.new("RGBA", logo.size, blue[:3] + (255,))
            flat.alpha_composite(logo)
            flat = flat.resize((self.size, self.size), Image.LANCZOS)
            return ImageTk.PhotoImage(flat.convert("RGB"), master=master)
        except Exception:
            return None

    def _style(self):
        if self._styled or not IS_WINDOWS:
            return
        self._styled = True
        try:
            import ctypes
            from . import win_effects
            hwnd = win_effects.hwnd_for(self.win)
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_TOPMOST = 0x00000008
            get = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            put = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            put(hwnd, GWL_EXSTYLE, get(hwnd, GWL_EXSTYLE) | WS_EX_NOACTIVATE
                | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
            win_effects.round_corners(self.win, "small")
        except Exception:
            pass

    def show(self, x, y):
        self.win.geometry("%dx%d+%d+%d" % (self.size, self.size, x, y))
        self.win.deiconify()
        self.win.lift()
        self._style()

    def hide(self):
        try:
            self.win.withdraw()
        except Exception:
            pass

    def box(self):
        """(x0, y0, x1, y1) on the screen, or None when hidden."""
        try:
            if not self.win.winfo_viewable():
                return None
            x, y = self.win.winfo_rootx(), self.win.winfo_rooty()
            return x, y, x + self.size, y + self.size
        except Exception:
            return None

    def destroy(self):
        try:
            self.win.destroy()
        except Exception:
            pass


_mac_target_class = []


class MacIcon:
    """The icon as a native panel that never activates Squint: shown over
    whatever app the text is in, clicked without taking the keyboard from
    it, and drawn by the system at the screen's own resolution."""

    def __init__(self, root, on_click):
        import objc
        from AppKit import (NSButton, NSColor, NSImage, NSMakeRect,
                            NSPanel)
        from Foundation import NSObject
        self.root = root
        self.on_click = on_click
        self.size = SIZE
        if not _mac_target_class:
            class SquintSelectIconTarget(NSObject):
                def initWithCallback_(self, callback):
                    self = objc.super(SquintSelectIconTarget, self).init()
                    if self is None:
                        return None
                    self._callback = callback
                    return self

                def click_(self, sender):
                    try:
                        self._callback()
                    except Exception:
                        pass
            _mac_target_class.append(SquintSelectIconTarget)
        self.target = _mac_target_class[0].alloc().initWithCallback_(
            self._clicked)
        borderless, nonactivating = 0, 1 << 7
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, SIZE, SIZE), borderless | nonactivating, 2,
            False)
        panel.setLevel_(25)                      # above normal windows
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setFloatingPanel_(True)
        # On every desktop, and over an app that is full screen.
        panel.setCollectionBehavior_((1 << 0) | (1 << 8))
        button = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, SIZE,
                                                            SIZE))
        button.setBordered_(False)
        button.setTitle_("")
        path = _logo_path()
        if path:
            image = NSImage.alloc().initWithContentsOfFile_(path)
            if image is not None:
                image.setSize_((SIZE, SIZE))
                button.setImage_(image)
                button.setImageScaling_(3)       # proportionally up or down
        button.setTarget_(self.target)
        button.setAction_("click:")
        panel.setContentView_(button)
        self.panel = panel
        self._at = None

    def _clicked(self):
        self.on_click()

    def show(self, x, y):
        from AppKit import NSScreen
        screens = NSScreen.screens()
        top = float(screens[0].frame().size.height) if screens else 0.0
        self.panel.setFrameOrigin_((float(x), top - float(y) - SIZE))
        self.panel.orderFrontRegardless()
        self._at = (int(x), int(y))

    def hide(self):
        try:
            self.panel.orderOut_(None)
        except Exception:
            pass
        self._at = None

    def box(self):
        if self._at is None:
            return None
        x, y = self._at
        return x, y, x + SIZE, y + SIZE

    def destroy(self):
        self.hide()


def make_icon(root, on_click):
    if IS_MAC:
        try:
            return MacIcon(root, on_click)
        except Exception:
            pass
    return TkIcon(root, on_click)


# -- Watching ---------------------------------------------------------------

def is_gesture(down, up, last_up, clicks):
    """Whether a press (`down`, `up`: (time, x, y)) made a selection: a
    drag, or the second or third click of a double or triple click.
    `clicks` is how many clicks in a row this one is."""
    if down is None or up is None:
        return False
    dx, dy = up[1] - down[1], up[2] - down[2]
    if (dx * dx + dy * dy) ** 0.5 >= DRAG:
        return True
    return clicks >= 2


class Watcher:
    """Watches for a selection and shows the icon. Everything runs on the
    Tk thread, from `after`, except asking a Mac for the selected text,
    which goes to a thread of its own.

    `on_click(text, handle)` is called when the icon is clicked: `text` is
    the selection when the system gave it (a Mac), else None, and `handle`
    is the app it is in (platform_util.front_handle). `blocked()` says
    when not to offer it at all - while a snip is being made, say."""

    def __init__(self, root, on_click, blocked=None, pressed=None,
                 pointer=None, front=None, is_text=None, read_text=None,
                 icon=None, log=None):
        self.root = root
        self.on_click = on_click
        self.blocked = blocked or (lambda: False)
        self._pressed = pressed
        self._pointer = pointer
        self._front = front
        self._is_text = is_text
        self._read_text = read_text
        self.icon = icon
        self._log = log
        self._said = {}
        self._job = None
        self._running = False
        self._down = None
        self._was_down = True       # a button held at start is not a press
        self._last_up = None
        self._clicks = 0
        self._text_at_down = False
        self._shown_at = 0.0
        self._offer = None          # (text, handle) the icon stands for
        self._asking = 0            # which gesture a Mac answer is for
        self._answer = None
        self._lock = threading.Lock()

    # -- the platform, replaceable for testing --
    def pressed(self):
        if self._pressed is not None:
            return bool(self._pressed())
        from . import click_watch
        backend = click_watch._pick_backend()
        return bool(backend()) if backend else False

    def pointer(self):
        if self._pointer is not None:
            return self._pointer()
        return self.root.winfo_pointerx(), self.root.winfo_pointery()

    def front(self):
        if self._front is not None:
            return self._front()
        from . import platform_util
        return platform_util.front_handle()

    def text_cursor(self):
        if self._is_text is not None:
            return bool(self._is_text())
        return windows_cursor_is_text()

    def read_text(self, handle, at=None):
        if self._read_text is not None:
            return self._read_text(handle)
        return mac_selected_text(handle, at)

    def over_squint(self, x, y):
        """Whether (x, y) is on one of Squint's own windows."""
        try:
            return self.root.winfo_containing(x, y) is not None
        except Exception:
            return False

    # -- life --
    def start(self):
        if self._running:
            return
        self._running = True
        self._was_down = True
        self._tick()

    def stop(self):
        self._running = False
        if self._job is not None:
            try:
                self.root.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        self.dismiss()

    def dismiss(self):
        self._offer = None
        if self.icon is not None:
            self.icon.hide()

    def _tick(self):
        self._job = None
        if not self._running:
            return
        try:
            self._step()
        except Exception:
            pass
        try:
            self._job = self.root.after(POLL, self._tick)
        except Exception:
            self._running = False

    def _on_icon(self, x, y):
        box = self.icon.box() if self.icon is not None else None
        return bool(box) and box[0] <= x <= box[2] and box[1] <= y <= box[3]

    def _step(self):
        now = time.monotonic()
        with self._lock:
            answer, self._answer = self._answer, None
        if answer is not None:
            self._answered(*answer)
        down = self.pressed()
        x, y = self.pointer()
        if down and not self._was_down:
            self._was_down = True
            on_icon = self._on_icon(x, y)
            if self._offer is not None and not on_icon:
                self.dismiss()
            if on_icon:
                self._down = None
                return
            last = self._last_up
            if last and now - last[0] <= DOUBLE and \
                    abs(x - last[1]) <= NEAR and abs(y - last[2]) <= NEAR:
                self._clicks += 1
            else:
                self._clicks = 1
            self._down = (now, x, y)
            # Windows: what the pointer looked like where the press began.
            self._text_at_down = self.text_cursor() if (
                IS_WINDOWS or self._is_text is not None) else False
        elif not down and self._was_down:
            self._was_down = False
            up = (now, x, y)
            press, self._down = self._down, None
            self._last_up = up
            if press is not None and is_gesture(press, up, None,
                                                self._clicks):
                self._gesture(press, up)
        if self._offer is not None and now - self._shown_at > SHOW_FOR \
                and not self._on_icon(x, y):
            self.dismiss()

    def note(self, what):
        """One line in the log for what became of a selection - never its
        text - and the same reason at most once in ten seconds, as people
        drag windows about all day."""
        if self._log is None:
            return
        now = time.monotonic()
        if what.startswith("not shown") and \
                now - self._said.get(what, -100.0) < 10.0:
            return
        self._said[what] = now
        try:
            self._log("select icon: %s" % what)
        except Exception:
            pass

    def _gesture(self, press, up):
        if self.blocked():
            self.note("not shown (Squint busy with a snip)")
            return
        if self.over_squint(press[1], press[2]):
            return
        handle = self.front()
        if not handle:
            self.note("not shown (Squint or the menu bar in front)")
            return                   # Squint itself, or the taskbar
        at = (up[1], up[2])
        if IS_MAC or self._read_text is not None:
            self._asking += 1
            ticket = self._asking

            def ask():
                text = ""
                try:
                    text = self.read_text(handle, (press[1], press[2])) \
                        or ""
                except Exception:
                    text = ""
                with self._lock:
                    self._answer = (ticket, text, handle, at)
            threading.Thread(target=ask, daemon=True,
                             name="selected-text").start()
            return
        if self._text_at_down:
            self._show(None, handle, at)
            self.note("shown (copied on click)")
        else:
            self.note("not shown (not begun on text)")

    def _answered(self, ticket, text, handle, at):
        if ticket != self._asking:
            return                   # a later selection has been made
        if text is True:
            # A selection the app would not describe: shown, and copied
            # from the app when clicked, as Ctrl+Cmd+C does.
            self._show(None, handle, at)
            self.note("shown")
            return
        text = (text or "").strip()
        if not text:
            self.note("not shown (the app reported no selection)")
            return
        if len(text) > LONGEST:
            self.note("not shown (selection too long)")
            return
        self._show(text, handle, at)
        self.note("shown")

    def _show(self, text, handle, at):
        if self.blocked():
            return
        if self.icon is None:
            self.icon = make_icon(self.root, self._clicked)
        x, y = at
        size = getattr(self.icon, "size", SIZE)
        try:
            sw, sh = self.root.winfo_screenwidth(), \
                self.root.winfo_screenheight()
            vx, vy = self.root.winfo_vrootx(), self.root.winfo_vrooty()
            vw, vh = self.root.winfo_vrootwidth(), \
                self.root.winfo_vrootheight()
            right, bottom = max(sw, vx + vw), max(sh, vy + vh)
        except Exception:
            right, bottom = 10 ** 5, 10 ** 5
        # The edges of the screen the selection is on, where they can be
        # asked: on a second monitor Tk's own answer is the first one's.
        try:
            from . import platform_util
            display = platform_util.display_for(int(x), int(y), 1, 1)
            if display is not None:
                right = int(display[0] + display[2])
                bottom = int(display[1] + display[3])
        except Exception:
            pass
        scale = getattr(self.icon, "scale", 1.0)
        ix = int(x + OFFSET[0] * scale)
        iy = int(y + OFFSET[1] * scale)
        if ix + size > right:
            ix = int(x - OFFSET[0] * scale - size)
        if iy + size > bottom:
            iy = int(y - OFFSET[1] * scale - size)
        self._offer = (text, handle)
        self._shown_at = time.monotonic()
        self.icon.show(ix, iy)

    def _clicked(self):
        offer = self._offer
        self.dismiss()
        if offer is None:
            return
        text, handle = offer
        try:
            self.on_click(text, handle)
        except Exception:
            pass
