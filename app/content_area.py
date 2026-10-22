"""Where the changing content is on screen, as opposed to the frame round it.

Hold-to-see translated the whole screen, and the whole screen is mostly
frame: the menu bar, the Dock or taskbar, and in the window itself the tab
strip, the address bar and the bookmarks. Those are the same on every
page, mostly already in the reader's language, and redrawn in another font
they came out mangled - "Bookmarks" split over two lines, the back and
forward arrows read as "<>C". They also came first, because they are at
the top, so the page itself was translated last.

This finds the part that changes: the page in a browser, the document in
a viewer or editor, and never the system bars. Everything outside it is
left as it is on screen.

macOS: the Accessibility interface (which Squint already has permission
for) is asked for the frontmost window; inside it, a browser's web area,
or failing that the largest scrolling area - the document in Preview, the
file list in Finder, the page in a word processor. The menu bar and Dock
are what the screen's visible frame leaves out.

Windows: the work area of the monitor leaves out the taskbar. In Chrome,
Edge, Brave and other Chromium browsers the page is its own child window,
which is found by its class name; elsewhere the window's client area,
which leaves out its title bar.

Every answer is a rectangle in the coordinates Tk places windows in
(points on a Mac, pixels on Windows), or None when it cannot be told - and
None only means "the whole screen", as before.
"""
import sys

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"


def _intersect(a, b):
    if a is None:
        return b
    if b is None:
        return a
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1 = min(a[0] + a[2], b[0] + b[2])
    y1 = min(a[1] + a[3], b[1] + b[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


def _contains(rect, px, py):
    return rect is not None and rect[0] <= px < rect[0] + rect[2] \
        and rect[1] <= py < rect[1] + rect[3]


def layers(px, py):
    """What is on the monitor under the pointer, most important first:
    {"monitor": the monitor less menu bar/Dock/taskbar, "window": the
    window in front on it, "content": the part of that window that
    changes (its page or document), "how": for the log}. Any may be None."""
    try:
        if IS_MAC:
            return _mac_layers(px, py)
        if IS_WINDOWS:
            return _windows_layers(px, py)
    except Exception as exc:
        return {"monitor": None, "window": None, "content": None,
                "how": "failed: %s" % str(exc)[:80]}
    return {"monitor": None, "window": None, "content": None, "how": "n/a"}


def find(px, py):
    """(content, how): the content rectangle for the pointer at px, py,
    and a word for the log saying how it was found."""
    try:
        if IS_MAC:
            return _mac(px, py)
        if IS_WINDOWS:
            return _windows(px, py)
    except Exception as exc:
        return None, "failed: %s" % str(exc)[:80]
    return None, "n/a"


# -- macOS -----------------------------------------------------------------

def _mac_visible_frame(px, py):
    """The screen under the pointer minus the menu bar and the Dock."""
    from AppKit import NSScreen
    screens = list(NSScreen.screens())
    if not screens:
        return None
    main_h = screens[0].frame().size.height
    for screen in screens:
        f = screen.frame()
        top = main_h - (f.origin.y + f.size.height)
        rect = (f.origin.x, top, f.size.width, f.size.height)
        if _contains(rect, px, py):
            v = screen.visibleFrame()
            vtop = main_h - (v.origin.y + v.size.height)
            return (v.origin.x, vtop, v.size.width, v.size.height)
    return None


class _AX:
    """The few Accessibility calls needed, through ctypes, as selection.py
    does: no extra framework to install."""

    def __init__(self):
        import ctypes
        import ctypes.util
        from ctypes import c_void_p, c_int32, c_long, c_char_p, c_bool
        self.ct = ctypes
        ax = ctypes.cdll.LoadLibrary(
            ctypes.util.find_library("ApplicationServices"))
        cf = ctypes.cdll.LoadLibrary(
            ctypes.util.find_library("CoreFoundation"))
        self.ax, self.cf = ax, cf
        ax.AXUIElementCreateApplication.restype = c_void_p
        ax.AXUIElementCreateApplication.argtypes = [c_int32]
        ax.AXUIElementCopyAttributeValue.restype = c_int32
        ax.AXUIElementCopyAttributeValue.argtypes = [
            c_void_p, c_void_p, ctypes.POINTER(c_void_p)]
        ax.AXValueGetValue.restype = c_bool
        ax.AXValueGetValue.argtypes = [c_void_p, c_int32, c_void_p]
        ax.AXUIElementSetMessagingTimeout.argtypes = [c_void_p,
                                                      ctypes.c_float]
        cf.CFStringCreateWithCString.restype = c_void_p
        cf.CFStringCreateWithCString.argtypes = [c_void_p, c_char_p,
                                                 ctypes.c_uint32]
        cf.CFStringGetCString.restype = c_bool
        cf.CFStringGetCString.argtypes = [c_void_p, c_char_p, c_long,
                                          ctypes.c_uint32]
        cf.CFArrayGetCount.restype = c_long
        cf.CFArrayGetCount.argtypes = [c_void_p]
        cf.CFArrayGetValueAtIndex.restype = c_void_p
        cf.CFArrayGetValueAtIndex.argtypes = [c_void_p, c_long]
        cf.CFGetTypeID.restype = c_long
        cf.CFGetTypeID.argtypes = [c_void_p]
        cf.CFArrayGetTypeID.restype = c_long
        cf.CFStringGetTypeID.restype = c_long
        cf.CFRelease.argtypes = [c_void_p]
        self._names = {}

    def name(self, text):
        if text not in self._names:
            self._names[text] = self.cf.CFStringCreateWithCString(
                None, text.encode("utf-8"), 0x08000100)
        return self._names[text]

    def get(self, element, attribute):
        out = self.ct.c_void_p()
        status = self.ax.AXUIElementCopyAttributeValue(
            element, self.name(attribute), self.ct.byref(out))
        return out.value if status == 0 else None

    def text(self, value):
        if not value or self.cf.CFGetTypeID(value) != \
                self.cf.CFStringGetTypeID():
            return ""
        buf = self.ct.create_string_buffer(256)
        if self.cf.CFStringGetCString(value, buf, 256, 0x08000100):
            return buf.value.decode("utf-8", "replace")
        return ""

    def children(self, element):
        value = self.get(element, "AXChildren")
        if not value or self.cf.CFGetTypeID(value) != \
                self.cf.CFArrayGetTypeID():
            return []
        return [self.cf.CFArrayGetValueAtIndex(value, i)
                for i in range(self.cf.CFArrayGetCount(value))]

    def switch_on(self, element, attribute):
        """Set a yes/no attribute to yes. False if the app refused."""
        try:
            if not hasattr(self, "_true"):
                self._true = self.ct.c_void_p.in_dll(self.cf,
                                                     "kCFBooleanTrue")
                self.ax.AXUIElementSetAttributeValue.restype = \
                    self.ct.c_int32
                self.ax.AXUIElementSetAttributeValue.argtypes = [
                    self.ct.c_void_p, self.ct.c_void_p, self.ct.c_void_p]
            return self.ax.AXUIElementSetAttributeValue(
                element, self.name(attribute), self._true) == 0
        except Exception:
            return False

    def children_of(self, element, attribute):
        value = self.get(element, attribute)
        if not value or self.cf.CFGetTypeID(value) != \
                self.cf.CFArrayGetTypeID():
            return []
        return [self.cf.CFArrayGetValueAtIndex(value, i)
                for i in range(self.cf.CFArrayGetCount(value))]

    def frame(self, element):
        class Point(self.ct.Structure):
            _fields_ = [("x", self.ct.c_double), ("y", self.ct.c_double)]
        pos, size = Point(), Point()
        p = self.get(element, "AXPosition")
        s = self.get(element, "AXSize")
        if not p or not s:
            return None
        if not self.ax.AXValueGetValue(p, 1, self.ct.byref(pos)):
            return None
        if not self.ax.AXValueGetValue(s, 2, self.ct.byref(size)):
            return None
        if size.x < 40 or size.y < 40:
            return None
        return (pos.x, pos.y, size.x, size.y)


_ax = {"obj": None}

CONTENT_ROLES = ("AXWebArea",)
SCROLL_ROLES = ("AXScrollArea",)


def _mac_app_under(px, py, monitor=None):
    """(pid, name) of the app owning the topmost ordinary window under the
    pointer, not counting Squint's own. Not simply the frontmost app: after
    a snip Squint itself is frontmost, and asking it for its window found
    nothing, so the whole screen - tabs, bookmarks and all - was
    translated."""
    import os
    try:
        import Quartz
        info = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID) or []
        me = os.getpid()
        for window in info:
            # Ordinary windows are layer 0; panels such as Quick Look float
            # a little above. The Dock, the menu bar and their friends are
            # 20 and up, and are never the thing being read.
            if not 0 <= int(window.get("kCGWindowLayer", 99)) < 20:
                continue
            pid = int(window.get("kCGWindowOwnerPID", 0))
            if pid == me:
                continue
            b = window.get("kCGWindowBounds") or {}
            rect = (float(b.get("X", 0)), float(b.get("Y", 0)),
                    float(b.get("Width", 0)), float(b.get("Height", 0)))
            # The window on top of this monitor, wherever the pointer is
            # on it: the app being read is the one in front. Small floating
            # things - a colour picker, a notification - are passed over.
            if rect[2] < 200 or rect[3] < 150:
                continue
            if monitor is not None and _intersect(rect, monitor) is None:
                continue
            if monitor is None and not _contains(rect, px, py):
                continue
            return pid, str(window.get("kCGWindowOwnerName") or "?"), rect
    except Exception:
        pass
    try:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is not None and int(app.processIdentifier()) != os.getpid():
            return int(app.processIdentifier()), \
                str(app.localizedName() or "?"), None
    except Exception:
        pass
    return None, None, None


# Roles worth looking inside for the content, and roles that are the frame:
# the tab strip, toolbars and bookmarks bar are hundreds of buttons, and
# walking into them used the whole search up before the page was reached.
_CONTAINERS = ("AXWindow", "AXGroup", "AXSplitGroup", "AXScrollArea",
               "AXLayoutArea", "AXUnknown", "AXBrowser", "AXTabGroup")
_FRAME = ("AXToolbar", "AXTabGroup", "AXMenuBar")


def _near(a, b, slack=12):
    return a is not None and b is not None and all(
        abs(x - y) <= slack for x, y in zip(a, b))


# Chrome, Brave, Edge and the other Chromium browsers, and apps built on
# Electron, describe their pages to the Accessibility interface only once
# something asks them to - until then there is no web area to find, and the
# tabs and bookmarks bar were translated along with the page. Asked once
# per running app; the first look may still miss, the next ones find it.
_CHROMIUM = ("com.google.Chrome", "com.brave.Browser", "com.microsoft.edgemac",
             "com.operasoftware.Opera", "com.vivaldi.Vivaldi",
             "org.chromium.Chromium", "com.google.Chrome.canary",
             "company.thebrowser.Browser")
_woken = set()


def _wake_chromium(ax, element, pid):
    if pid in _woken:
        return
    _woken.add(pid)
    try:
        from AppKit import NSRunningApplication
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(
            pid)
        bundle = str(app.bundleIdentifier() or "") if app else ""
    except Exception:
        bundle = ""
    if bundle.startswith(_CHROMIUM) or "electron" in bundle.lower():
        ax.switch_on(element, "AXManualAccessibility")
        ax.switch_on(element, "AXEnhancedUserInterface")


def _mac_window_content(px, py, monitor=None):
    pid, name, bounds = _mac_app_under(px, py, monitor)
    if pid is None:
        return None, None, "no window under the pointer"
    if _ax["obj"] is None:
        _ax["obj"] = _AX()
    ax = _ax["obj"]
    element = ax.ax.AXUIElementCreateApplication(pid)
    try:
        ax.ax.AXUIElementSetMessagingTimeout(element, 0.25)
    except Exception:
        pass
    _wake_chromium(ax, element, pid)
    window = None
    for candidate in [ax.get(element, "AXFocusedWindow")] + \
            ax.children_of(element, "AXWindows"):
        if candidate and (bounds is None or _near(ax.frame(candidate),
                                                   bounds)):
            window = candidate
            break
    if not window:
        return bounds, None, "no window (%s)" % name
    window_rect = ax.frame(window) or bounds
    web, scroll, frame_bottom = None, [], None
    import time
    queue, seen = [(window, 0)], 0
    deadline = time.monotonic() + 0.5     # never hold up the press long
    while queue and seen < 600 and time.monotonic() < deadline:
        node, depth = queue.pop(0)
        seen += 1
        role = ax.text(ax.get(node, "AXRole"))
        if role in CONTENT_ROLES:
            web = ax.frame(node)
            if web:
                break
        if role in SCROLL_ROLES:
            rect = ax.frame(node)
            if rect:
                scroll.append(rect)
        if role in _FRAME and window_rect is not None:
            rect = ax.frame(node) if role != "AXTabGroup" else None
            # A toolbar in the top third is part of the frame above the
            # content; its bottom is where the content can start.
            if rect and rect[1] < window_rect[1] + window_rect[3] / 3.0:
                bottom = rect[1] + rect[3]
                frame_bottom = max(frame_bottom or 0, bottom)
        # Tab groups are entered: Safari keeps the page inside one. Their
        # tabs are buttons, which are not.
        if depth < 10 and role in _CONTAINERS:
            queue.extend((child, depth + 1) for child in ax.children(node))
    if web:
        return window_rect, web, "web area (%s)" % name
    if scroll:
        biggest = max(scroll, key=lambda r: r[2] * r[3])
        if window_rect and biggest[2] * biggest[3] >= \
                0.25 * window_rect[2] * window_rect[3]:
            return window_rect, biggest, "scroll area (%s)" % name
    if frame_bottom and window_rect:
        top = frame_bottom
        below = (window_rect[0], top, window_rect[2],
                 window_rect[1] + window_rect[3] - top)
        if below[3] > 100:
            return window_rect, below, "below the toolbars (%s)" % name
    return window_rect, None, "window (%s)" % name


def _mac_layers(px, py):
    visible = _mac_visible_frame(px, py)
    window, content, how = _mac_window_content(px, py, visible)
    whole = _intersect(window, visible) if window else None
    inner = _intersect(content, visible) if content and whole else None
    # A content area much smaller than its window - a side panel, a
    # sidebar, a second pane - is not the document: the window is.
    if inner and whole and inner[2] * inner[3] < 0.35 * whole[2] * whole[3]:
        inner, how = None, "window (%s)" % how
    return {"monitor": visible, "window": whole,
            "content": inner or whole, "how": how}


def _mac(px, py):
    layers = _mac_layers(px, py)
    return layers["content"] or layers["monitor"], layers["how"]


# -- Windows ---------------------------------------------------------------

_windows_last = {"window": None, "monitor": None}


def _windows_layers(px, py):
    _windows_last.update(window=None, monitor=None)
    content, how = _windows(px, py)
    return {"monitor": _windows_last["monitor"] or content,
            "window": _windows_last["window"], "content": content,
            "how": how}


def _windows(px, py):
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    def as_rect(r):
        return (r.left, r.top, r.right - r.left, r.bottom - r.top)

    point = wintypes.POINT(int(px), int(py))
    user32.MonitorFromPoint.restype = wintypes.HANDLE
    monitor = user32.MonitorFromPoint(point, 2)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    work = None
    if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        work = as_rect(info.rcWork)

    user32.GetAncestor.restype = wintypes.HWND
    user32.GetForegroundWindow.restype = wintypes.HWND
    top = None
    # The window in front, if it is on this monitor; otherwise the one
    # under the pointer.
    front = user32.GetForegroundWindow()
    if front:
        rect = wintypes.RECT()
        user32.GetWindowRect(front, ctypes.byref(rect))
        if _intersect(as_rect(rect), work) is not None and \
                user32.IsWindowVisible(front) and \
                not user32.IsIconic(front):
            top = front
    if not top:
        user32.WindowFromPoint.restype = wintypes.HWND
        hwnd = user32.WindowFromPoint(point)
        top = user32.GetAncestor(hwnd, 2) if hwnd else None
    if not top:
        return work, "work area"
    frame = wintypes.RECT()
    user32.GetWindowRect(top, ctypes.byref(frame))
    _windows_last["window"] = _intersect(as_rect(frame), work)
    _windows_last["monitor"] = work

    found = []
    buf = ctypes.create_unicode_buffer(256)
    PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(child, _lparam):
        user32.GetClassNameW(child, buf, 256)
        if buf.value == "Chrome_RenderWidgetHostHWND" and \
                user32.IsWindowVisible(child):
            rect = wintypes.RECT()
            user32.GetWindowRect(child, ctypes.byref(rect))
            if rect.right - rect.left > 100 and rect.bottom - rect.top > 100:
                found.append(as_rect(rect))
        return True

    user32.EnumChildWindows(top, PROC(visit), 0)
    if found:
        best = max(found, key=lambda r: r[2] * r[3])
        return _intersect(best, work), "browser page"

    # The client area: the window without its title bar and borders.
    rect = wintypes.RECT()
    user32.GetClientRect(top, ctypes.byref(rect))
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(top, ctypes.byref(origin))
    client = (origin.x, origin.y, rect.right, rect.bottom)
    if client[2] > 100 and client[3] > 100:
        return _intersect(client, work), "window"
    return work, "work area"
